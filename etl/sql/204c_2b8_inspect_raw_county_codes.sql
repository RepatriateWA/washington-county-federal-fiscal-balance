
-- ETL-204C-2B.8
-- Inspect original Railroad Retirement geographic values
-- READ ONLY

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT
    v.action_date_fiscal_year AS fiscal_year,
    substring(
        upper(v.assistance_award_unique_key)
        FROM 'WA\*\*([0-9]{3})'
    ) AS award_key_county,
    r.raw_record ->>
        'prime_award_transaction_place_of_performance_county_fips_code'
        AS performance_county_raw,
    r.raw_record ->>
        'prime_award_transaction_recipient_county_fips_code'
        AS recipient_county_raw,
    r.raw_record ->>
        'primary_place_of_performance_county_name'
        AS performance_county_name,
    r.raw_record ->>
        'recipient_county_name'
        AS recipient_county_name,
    r.raw_record ->>
        'primary_place_of_performance_code'
        AS performance_code
FROM analysis.v_certified_assistance_ledger v
JOIN assistance.award_transaction_observation o
    ON o.assistance_transaction_id =
       v.assistance_transaction_id
JOIN assistance.raw_award_transaction r
    ON r.raw_assistance_transaction_id =
       o.raw_assistance_transaction_id
WHERE v.load_batch_id IN (20, 21)
  AND TRIM(v.cfda_number) = '57.001'
ORDER BY
    v.action_date_fiscal_year,
    v.assistance_transaction_id
LIMIT 20;

COMMIT;
