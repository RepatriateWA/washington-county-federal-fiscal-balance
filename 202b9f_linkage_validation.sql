BEGIN TRANSACTION READ ONLY;

SELECT
    raw.load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(obs.raw_award_transaction_id) AS linked_observations,
    COUNT(*) FILTER (
        WHERE obs.raw_award_transaction_id IS NULL
    ) AS unlinked_observations,
    COUNT(*) FILTER (
        WHERE obs.award_transaction_id
              IS DISTINCT FROM tx.award_transaction_id
    ) AS incorrect_links
FROM procurement.raw_award_transaction raw
LEFT JOIN procurement.award_transaction_observation obs
    ON obs.raw_award_transaction_id =
       raw.raw_award_transaction_id
LEFT JOIN procurement.award_transaction tx
    ON tx.usaspending_transaction_id =
       raw.raw_record ->> 'contract_transaction_unique_key'
GROUP BY raw.load_batch_id
ORDER BY raw.load_batch_id;

SELECT
    COUNT(*) AS total_links,
    COUNT(DISTINCT raw_award_transaction_id)
        AS distinct_raw_observations,
    COUNT(DISTINCT award_transaction_id)
        AS distinct_canonical_transactions
FROM procurement.award_transaction_observation;

SELECT
    COUNT(*) AS canonical_transactions,
    COALESCE(SUM(federal_action_obligation), 0)
        AS total_canonical_obligations
FROM procurement.award_transaction;

COMMIT;
