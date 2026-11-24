BEGIN;
SET TRANSACTION READ ONLY;

WITH historical_awards AS (
    SELECT DISTINCT
        load_batch_id,
        assistance_award_unique_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    historical.load_batch_id,
    COUNT(*) AS distinct_raw_awards,
    COUNT(award.assistance_award_id)
        AS existing_canonical_awards,
    COUNT(*) - COUNT(award.assistance_award_id)
        AS missing_canonical_awards
FROM historical_awards AS historical
LEFT JOIN assistance.award AS award
    ON award.assistance_award_unique_key =
       historical.assistance_award_unique_key
GROUP BY historical.load_batch_id
ORDER BY historical.load_batch_id;

ROLLBACK;
