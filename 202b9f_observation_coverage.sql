BEGIN TRANSACTION READ ONLY;

WITH coverage AS (
    SELECT
        raw.load_batch_id,
        COUNT(*) AS raw_rows,
        COUNT(tx.award_transaction_id) AS matched_transactions,
        COUNT(*) FILTER (
            WHERE tx.award_transaction_id IS NULL
        ) AS unmatched_transactions,
        COUNT(*) FILTER (
            WHERE tx.award_transaction_id IS NOT NULL
              AND aw.generated_unique_award_id
                  IS DISTINCT FROM
                  raw.raw_record ->> 'contract_award_unique_key'
        ) AS award_identity_mismatches
    FROM procurement.raw_award_transaction raw
    LEFT JOIN procurement.award_transaction tx
        ON tx.usaspending_transaction_id =
           raw.raw_record ->> 'contract_transaction_unique_key'
    LEFT JOIN procurement.award aw
        ON aw.award_id = tx.award_id
    GROUP BY raw.load_batch_id
)
SELECT *
FROM coverage
ORDER BY load_batch_id;

COMMIT;
