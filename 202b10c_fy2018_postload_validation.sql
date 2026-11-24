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
WHERE load_batch_id = 22
GROUP BY load_batch_id;

SELECT
    COUNT(*) AS canonical_transactions,
    COALESCE(SUM(federal_action_obligation), 0)
        AS canonical_obligations
FROM procurement.award_transaction;

SELECT
    COUNT(*) AS total_raw_observations
FROM procurement.raw_award_transaction;

SELECT
    COUNT(*) AS provenance_links
FROM procurement.award_transaction_observation;

COMMIT;
