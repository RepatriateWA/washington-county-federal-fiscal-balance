-- ETL-237A
-- Raw procurement annual controls
-- READ ONLY

BEGIN TRANSACTION READ ONLY;

SELECT
    fiscal_year,
    COUNT(*) AS transaction_rows,
    ROUND(SUM(federal_action_obligation), 2)
        AS gross_obligations_usd,
    COUNT(DISTINCT award_id)
        AS distinct_awards,
    COUNT(DISTINCT load_batch_id)
        AS load_batches
FROM procurement.award_transaction
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

ROLLBACK;