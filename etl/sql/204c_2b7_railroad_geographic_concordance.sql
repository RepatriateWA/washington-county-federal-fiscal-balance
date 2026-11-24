
-- ============================================================
-- WCFFBP ETL-204C-2B.7 - CORRECTED
-- HISTORICAL RAILROAD GEOGRAPHIC CONCORDANCE
-- FY2018-FY2019
-- STRICTLY READ ONLY
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT
    'ETL-204C-2B.7 - GEOGRAPHIC CONCORDANCE'
    AS diagnostic;

SELECT
    current_setting('transaction_read_only')
    AS read_only_status;

-- ============================================================
-- 1. Extract source observations and compare geographic codes
-- ============================================================

WITH railroad AS (
    SELECT
        v.assistance_transaction_id,
        v.action_date_fiscal_year AS fiscal_year,
        v.federal_action_obligation AS obligation,
        v.assistance_award_unique_key AS award_key,

        substring(
            upper(v.assistance_award_unique_key)
            FROM 'WA\*\*([0-9]{3})'
        ) AS key_county,

        r.raw_record ->>
            'prime_award_transaction_place_of_performance_state_fips_code'
            AS performance_state,

        r.raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'
            AS performance_county,

        r.raw_record ->>
            'prime_award_transaction_recipient_state_fips_code'
            AS recipient_state,

        r.raw_record ->>
            'prime_award_transaction_recipient_county_fips_code'
            AS recipient_county

    FROM analysis.v_certified_assistance_ledger v

    JOIN assistance.award_transaction_observation o
      ON o.assistance_transaction_id =
         v.assistance_transaction_id

    JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         o.raw_assistance_transaction_id

    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
),

normalized AS (
    SELECT
        *,
        CASE
            WHEN TRIM(performance_county) ~ '^[0-9]{1,3}$'
            THEN LPAD(TRIM(performance_county), 3, '0')
        END AS perf_county_3,

        CASE
            WHEN TRIM(recipient_county) ~ '^[0-9]{1,3}$'
            THEN LPAD(TRIM(recipient_county), 3, '0')
        END AS recip_county_3

    FROM railroad
)

SELECT
    fiscal_year,

    COUNT(*) AS source_observations,

    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,

    COUNT(*) FILTER (
        WHERE key_county = perf_county_3
    ) AS key_matches_performance,

    COUNT(*) FILTER (
        WHERE key_county = recip_county_3
    ) AS key_matches_recipient,

    COUNT(*) FILTER (
        WHERE perf_county_3 = recip_county_3
    ) AS performance_matches_recipient,

    COUNT(*) FILTER (
        WHERE key_county IS DISTINCT FROM perf_county_3
    ) AS key_performance_disagreements,

    COUNT(*) FILTER (
        WHERE key_county IS DISTINCT FROM recip_county_3
    ) AS key_recipient_disagreements,

    COUNT(*) FILTER (
        WHERE performance_state = '53'
          AND recipient_state = '53'
    ) AS both_states_washington

FROM normalized
GROUP BY fiscal_year
ORDER BY fiscal_year;


-- ============================================================
-- 2. Examine raw state FIPS values
-- ============================================================

SELECT
    v.action_date_fiscal_year AS fiscal_year,

    r.raw_record ->>
        'prime_award_transaction_place_of_performance_state_fips_code'
        AS performance_state,

    r.raw_record ->>
        'prime_award_transaction_recipient_state_fips_code'
        AS recipient_state,

    COUNT(*) AS observations

FROM analysis.v_certified_assistance_ledger v

JOIN assistance.award_transaction_observation o
  ON o.assistance_transaction_id =
     v.assistance_transaction_id

JOIN assistance.raw_award_transaction r
  ON r.raw_assistance_transaction_id =
     o.raw_assistance_transaction_id

WHERE v.load_batch_id IN (20, 21)
  AND TRIM(v.cfda_number) = '57.001'

GROUP BY
    v.action_date_fiscal_year,
    performance_state,
    recipient_state

ORDER BY
    fiscal_year,
    performance_state,
    recipient_state;


COMMIT;

SELECT
    'ETL-204C-2B.7 COMPLETE - NO DATABASE WRITES'
    AS status;
