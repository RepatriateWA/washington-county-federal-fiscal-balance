
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '========================================================'
\echo 'ETL-223G - HISTORICAL DIMENSION LINKAGE PREFLIGHT'
\echo 'FY2018-FY2019 / READ ONLY'
\echo '========================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. TRANSACTION AND AWARD LINKAGE COVERAGE'

SELECT
    t.load_batch_id,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (WHERE t.recipient_id IS NOT NULL)
        AS transaction_recipient_links,
    COUNT(*) FILTER (WHERE t.awarding_agency_id IS NOT NULL)
        AS transaction_awarding_links,
    COUNT(*) FILTER (WHERE t.funding_agency_id IS NOT NULL)
        AS transaction_funding_links,
    COUNT(*) FILTER (WHERE a.recipient_id IS NOT NULL)
        AS award_recipient_links,
    COUNT(*) FILTER (WHERE a.awarding_agency_id IS NOT NULL)
        AS award_awarding_links,
    COUNT(*) FILTER (WHERE a.funding_agency_id IS NOT NULL)
        AS award_funding_links
FROM assistance.award_transaction t
JOIN assistance.award a
  ON a.assistance_award_id = t.assistance_award_id
WHERE t.load_batch_id IN (20, 21)
GROUP BY t.load_batch_id
ORDER BY t.load_batch_id;

\echo ''
\echo '2. EXISTING AGENCY DIMENSION CODE MATCHES'
\echo 'Distinct raw agency codes; not transaction links'

WITH raw_codes AS (
    SELECT DISTINCT
        r.load_batch_id,
        x.agency_role,
        NULLIF(BTRIM(r.raw_record ->> x.field_name), '')
            AS agency_code
    FROM assistance.raw_award_transaction r
    CROSS JOIN (
        VALUES
            ('AWARDING', 'awarding_agency_code'),
            ('AWARDING_SUB', 'awarding_sub_agency_code'),
            ('FUNDING', 'funding_agency_code'),
            ('FUNDING_SUB', 'funding_sub_agency_code')
    ) AS x(agency_role, field_name)
    WHERE r.load_batch_id IN (20, 21)
)
SELECT
    rc.load_batch_id,
    rc.agency_role,
    COUNT(*) FILTER (WHERE rc.agency_code IS NOT NULL)
        AS distinct_populated_codes,
    COUNT(*) FILTER (
        WHERE rc.agency_code IS NOT NULL
          AND a.agency_id IS NOT NULL
    ) AS existing_dimension_matches,
    COUNT(*) FILTER (
        WHERE rc.agency_code IS NOT NULL
          AND a.agency_id IS NULL
    ) AS codes_not_in_dimension
FROM raw_codes rc
LEFT JOIN procurement.agency a
  ON a.agency_code = rc.agency_code
GROUP BY rc.load_batch_id, rc.agency_role
ORDER BY rc.load_batch_id, rc.agency_role;

\echo ''
\echo '3. EXISTING RECIPIENT IDENTITY INDICATORS'

SELECT
    r.load_batch_id,
    COUNT(*) AS raw_records,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(r.raw_record ->> 'recipient_name'), '')
              IS NOT NULL
    ) AS populated_names,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(r.raw_record ->> 'recipient_uei'), '')
              IS NOT NULL
    ) AS populated_ueis,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(r.raw_record ->> 'recipient_duns'), '')
              IS NOT NULL
    ) AS populated_duns,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(r.raw_record ->> 'recipient_state_code'), '')
              IS NOT NULL
    ) AS populated_states,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(r.raw_record ->> 'recipient_city_name'), '')
              IS NOT NULL
    ) AS populated_cities
FROM assistance.raw_award_transaction r
WHERE r.load_batch_id IN (20, 21)
GROUP BY r.load_batch_id
ORDER BY r.load_batch_id;

\echo ''
\echo '4. EXISTING SHARED RECIPIENT DIMENSION COVERAGE'

SELECT
    COUNT(*) AS total_recipients,
    COUNT(*) FILTER (
        WHERE recipient_identity_key IS NOT NULL
    ) AS with_identity_key,
    COUNT(*) FILTER (
        WHERE recipient_uei IS NOT NULL
    ) AS with_uei,
    COUNT(*) FILTER (
        WHERE recipient_name IS NOT NULL
    ) AS with_name
FROM procurement.recipient;

\echo ''
\echo '5. EXISTING SHARED AGENCY DIMENSION COVERAGE'

SELECT
    COUNT(*) AS total_agencies,
    COUNT(*) FILTER (
        WHERE agency_code IS NOT NULL
    ) AS with_code,
    COUNT(*) FILTER (
        WHERE agency_name IS NOT NULL
    ) AS with_name
FROM procurement.agency;

COMMIT;

\echo 'ETL-223G COMPLETE - NO DATABASE WRITES'
