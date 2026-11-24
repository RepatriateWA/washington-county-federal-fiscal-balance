BEGIN;
SET TRANSACTION READ ONLY;

SELECT
    raw.load_batch_id,
    COALESCE(
        NULLIF(BTRIM(raw.raw_record ->> 'cfda_number'), ''),
        '<BLANK>'
    ) AS source_listing_code,
    COUNT(*) AS transaction_rows,
    COUNT(DISTINCT raw.assistance_award_unique_key)
        AS distinct_awards
FROM assistance.raw_award_transaction AS raw
LEFT JOIN assistance.assistance_listing AS listing
    ON listing.cfda_number =
       BTRIM(raw.raw_record ->> 'cfda_number')
WHERE raw.load_batch_id IN (20, 21)
  AND listing.assistance_listing_id IS NULL
GROUP BY
    raw.load_batch_id,
    COALESCE(
        NULLIF(BTRIM(raw.raw_record ->> 'cfda_number'), ''),
        '<BLANK>'
    )
ORDER BY raw.load_batch_id, transaction_rows DESC;

ROLLBACK;
