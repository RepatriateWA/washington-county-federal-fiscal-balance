\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-209Z - SNAP HISTORICAL EVIDENCE'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo '1. HISTORICAL AWARD, RECIPIENT AND GEOGRAPHY'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), '')
    ) AS award_identifier,
    recipient_name,
    awarding_agency_name,
    funding_agency_name,
    performance_state_code,
    performance_county_fips,
    canonical_award_description,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '10.551'
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
GROUP BY
    action_date_fiscal_year,
    award_id_fain,
    award_id_uri,
    recipient_name,
    awarding_agency_name,
    funding_agency_name,
    performance_state_code,
    performance_county_fips,
    canonical_award_description
ORDER BY fiscal_year, net_obligations DESC;

\echo '2. HISTORICAL TRANSACTION DESCRIPTIONS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    assistance_transaction_id,
    award_id_fain,
    federal_action_obligation AS obligation,
    recipient_name,
    transaction_description,
    is_covid
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '10.551'
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
ORDER BY fiscal_year, award_id_fain,
         assistance_transaction_id;

\echo '3. GEOGRAPHIC AND COVID SUMMARY'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COALESCE(performance_state_code, '[NULL]')
        AS performance_state,
    COALESCE(BTRIM(performance_county_fips), '[NULL]')
        AS performance_county,
    COALESCE(is_covid, false) AS covid_flag,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '10.551'
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
GROUP BY 1, 2, 3, 4
ORDER BY fiscal_year, net_obligations DESC;

COMMIT;

\echo 'ETL-209Z COMPLETE - READ ONLY'