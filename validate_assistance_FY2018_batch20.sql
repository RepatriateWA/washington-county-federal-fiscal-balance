BEGIN;
SET TRANSACTION READ ONLY;

SELECT
    lb.load_batch_id,
    lb.fiscal_year_start,
    lb.fiscal_year_end,
    lb.load_status,
    lb.source_record_count,
    lb.loaded_record_count,
    COUNT(raw.raw_assistance_transaction_id) AS database_rows,
    COUNT(DISTINCT raw.assistance_transaction_unique_key)
        AS distinct_transaction_keys,
    COUNT(DISTINCT raw.assistance_award_unique_key)
        AS distinct_award_keys,
    lb.source_file,
    lb.file_sha256
FROM procurement.load_batch AS lb
LEFT JOIN assistance.raw_award_transaction AS raw
    ON raw.load_batch_id = lb.load_batch_id
WHERE lb.load_batch_id = 20
GROUP BY
    lb.load_batch_id,
    lb.fiscal_year_start,
    lb.fiscal_year_end,
    lb.load_status,
    lb.source_record_count,
    lb.loaded_record_count,
    lb.source_file,
    lb.file_sha256;

SELECT
    raw.raw_record ->> 'action_date_fiscal_year'
        AS action_fiscal_year,
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (
        WHERE raw.raw_record ->>
            'prime_award_transaction_place_of_performance_state_fips_code'
            = '53'
    ) AS washington_performance_rows,
    COUNT(*) FILTER (
        WHERE raw.raw_record ->> 'recipient_state_code' = 'WA'
    ) AS washington_recipient_rows
FROM assistance.raw_award_transaction AS raw
WHERE raw.load_batch_id = 20
GROUP BY 1
ORDER BY 1;

ROLLBACK;
