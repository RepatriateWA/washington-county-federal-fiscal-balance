BEGIN TRANSACTION READ ONLY;

SELECT
    load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(*) FILTER (
        WHERE NULLIF(
            raw_record ->> 'contract_transaction_unique_key', ''
        ) IS NULL
    ) AS missing_transaction_keys,
    COUNT(*) FILTER (
        WHERE NULLIF(
            raw_record ->> 'contract_award_unique_key', ''
        ) IS NULL
    ) AS missing_award_keys
FROM procurement.raw_award_transaction
WHERE load_batch_id IN (22, 23)
GROUP BY load_batch_id
ORDER BY load_batch_id;

SELECT
    COUNT(*) AS total_raw_observations
FROM procurement.raw_award_transaction;

SELECT
    COUNT(*) AS canonical_transactions,
    COALESCE(SUM(federal_action_obligation), 0)
        AS canonical_obligations
FROM procurement.award_transaction;

SELECT
    COUNT(*) AS existing_provenance_links
FROM procurement.award_transaction_observation;

SELECT
    raw.load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(tx.award_transaction_id) AS existing_canonical_matches,
    COUNT(*) FILTER (
        WHERE tx.award_transaction_id IS NULL
    ) AS awaiting_normalization
FROM procurement.raw_award_transaction raw
LEFT JOIN procurement.award_transaction tx
    ON tx.usaspending_transaction_id =
       raw.raw_record ->> 'contract_transaction_unique_key'
WHERE raw.load_batch_id IN (22, 23)
GROUP BY raw.load_batch_id
ORDER BY raw.load_batch_id;

COMMIT;
