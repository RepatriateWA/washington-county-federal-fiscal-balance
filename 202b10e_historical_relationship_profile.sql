BEGIN TRANSACTION READ ONLY;

WITH historical AS (
    SELECT
        load_batch_id,
        raw_record ->> 'contract_transaction_unique_key'
            AS transaction_key,
        raw_record ->> 'contract_award_unique_key'
            AS award_key
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
)
SELECT
    h.load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(DISTINCT h.transaction_key)
        AS distinct_transaction_keys,
    COUNT(DISTINCT h.award_key)
        AS distinct_award_keys,
    COUNT(DISTINCT h.award_key) FILTER (
        WHERE a.award_id IS NOT NULL
    ) AS existing_award_keys,
    COUNT(DISTINCT h.award_key) FILTER (
        WHERE a.award_id IS NULL
    ) AS missing_award_keys,
    COUNT(*) FILTER (
        WHERE t.award_transaction_id IS NOT NULL
    ) AS existing_transactions,
    COUNT(*) FILTER (
        WHERE t.award_transaction_id IS NOT NULL
          AND t.award_id IS DISTINCT FROM a.award_id
    ) AS existing_transaction_award_mismatches
FROM historical h
LEFT JOIN procurement.award a
    ON a.usaspending_award_id = h.award_key
LEFT JOIN procurement.award_transaction t
    ON t.usaspending_transaction_id = h.transaction_key
GROUP BY h.load_batch_id
ORDER BY h.load_batch_id;

COMMIT;
