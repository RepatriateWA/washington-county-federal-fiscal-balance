BEGIN TRANSACTION READ ONLY;

SELECT
    COUNT(*) AS canonical_transactions,
    COALESCE(SUM(federal_action_obligation), 0)
        AS canonical_obligations
FROM procurement.award_transaction;

SELECT
    COUNT(*) AS raw_observations
FROM procurement.raw_award_transaction;

SELECT
    COUNT(*) AS provenance_links
FROM procurement.award_transaction_observation;

COMMIT;
