BEGIN;
SET TRANSACTION READ ONLY;

SELECT
    raw.load_batch_id,
    BTRIM(raw.raw_record ->> 'cfda_number') AS cfda_number,
    BTRIM(raw.raw_record ->> 'cfda_title') AS observed_title,
    COUNT(*) AS observation_count
FROM assistance.raw_award_transaction AS raw
LEFT JOIN assistance.assistance_listing AS existing
    ON existing.cfda_number =
       BTRIM(raw.raw_record ->> 'cfda_number')
WHERE raw.load_batch_id IN (20, 21)
  AND existing.assistance_listing_id IS NULL
GROUP BY
    raw.load_batch_id,
    BTRIM(raw.raw_record ->> 'cfda_number'),
    BTRIM(raw.raw_record ->> 'cfda_title')
ORDER BY
    cfda_number,
    raw.load_batch_id,
    observation_count DESC;

ROLLBACK;
