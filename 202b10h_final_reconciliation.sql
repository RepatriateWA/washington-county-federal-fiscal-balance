BEGIN TRANSACTION READ ONLY;

WITH compared AS (
    SELECT
        r.load_batch_id AS raw_batch_id,
        r.raw_record ->> 'contract_transaction_unique_key'
            AS transaction_key,
        NULLIF(
            BTRIM(r.raw_record ->> 'federal_action_obligation'),
            ''
        )::numeric AS raw_obligation,
        t.award_transaction_id,
        t.load_batch_id AS canonical_batch_id,
        t.federal_action_obligation AS canonical_obligation
    FROM procurement.raw_award_transaction r
    LEFT JOIN procurement.award_transaction t
        ON t.usaspending_transaction_id =
           r.raw_record ->> 'contract_transaction_unique_key'
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    raw_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(*) FILTER (
        WHERE award_transaction_id IS NOT NULL
    ) AS matched_transactions,
    COUNT(*) FILTER (
        WHERE award_transaction_id IS NULL
    ) AS missing_transactions,
    COUNT(*) FILTER (
        WHERE canonical_batch_id = raw_batch_id
    ) AS canonical_in_same_batch,
    COUNT(*) FILTER (
        WHERE canonical_batch_id IS DISTINCT FROM raw_batch_id
          AND award_transaction_id IS NOT NULL
    ) AS canonical_from_other_batch,
    COUNT(*) FILTER (
        WHERE award_transaction_id IS NOT NULL
          AND raw_obligation IS DISTINCT FROM canonical_obligation
    ) AS obligation_mismatches,
    ROUND(SUM(raw_obligation), 2) AS raw_net_obligations,
    ROUND(
        SUM(canonical_obligation) FILTER (
            WHERE award_transaction_id IS NOT NULL
        ), 2
    ) AS matched_canonical_net_obligations
FROM compared
GROUP BY ROLLUP(raw_batch_id)
ORDER BY raw_batch_id NULLS LAST;

COMMIT;