
-- ETL-204C-2B.9
-- Corrected five-digit county FIPS concordance
-- READ ONLY

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

WITH evidence AS (
    SELECT
        v.action_date_fiscal_year AS fiscal_year,
        v.assistance_transaction_id,
        v.federal_action_obligation,
        '53' || substring(
            upper(v.assistance_award_unique_key)
            FROM 'WA\*\*([0-9]{3})'
        ) AS award_full_fips,
        NULLIF(TRIM(r.raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'), '')
            AS performance_full_fips,
        NULLIF(TRIM(r.raw_record ->>
            'prime_award_transaction_recipient_county_fips_code'), '')
            AS recipient_full_fips
    FROM analysis.v_certified_assistance_ledger v
    JOIN assistance.award_transaction_observation o
      ON o.assistance_transaction_id =
         v.assistance_transaction_id
    JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         o.raw_assistance_transaction_id
    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
)
SELECT
    fiscal_year,
    COUNT(*) AS observations,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(*) FILTER (
        WHERE award_full_fips = performance_full_fips
    ) AS award_performance_matches,
    COUNT(*) FILTER (
        WHERE award_full_fips = recipient_full_fips
    ) AS award_recipient_matches,
    COUNT(*) FILTER (
        WHERE performance_full_fips = recipient_full_fips
    ) AS performance_recipient_matches,
    COUNT(*) FILTER (
        WHERE award_full_fips IS DISTINCT FROM performance_full_fips
           OR award_full_fips IS DISTINCT FROM recipient_full_fips
    ) AS disagreements,
    SUM(federal_action_obligation)
        AS net_obligations
FROM evidence
GROUP BY fiscal_year
ORDER BY fiscal_year;

COMMIT;
