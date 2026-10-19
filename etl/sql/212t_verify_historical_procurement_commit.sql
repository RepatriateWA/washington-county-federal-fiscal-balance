
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-212T - HISTORICAL PROCUREMENT POST-COMMIT AUDIT'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '180s';

WITH historical AS MATERIALIZED (
    SELECT
        r.load_batch_id,
        r.raw_award_transaction_id,
        a.award_transaction_id
    FROM procurement.raw_award_transaction r
    LEFT JOIN procurement.award_transaction a
      ON a.usaspending_transaction_id =
         NULLIF(BTRIM(r.raw_record ->> 'contract_transaction_unique_key'), '')
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    h.load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(h.award_transaction_id) AS canonical_matches,
    COUNT(o.raw_award_transaction_id) AS observation_links,
    COUNT(pop.award_transaction_id) AS geography_links,
    COUNT(*) FILTER (
        WHERE o.raw_award_transaction_id IS NULL
    ) AS missing_observations,
    COUNT(*) FILTER (
        WHERE pop.award_transaction_id IS NULL
    ) AS missing_geography,
    COUNT(*) FILTER (
        WHERE pop.award_transaction_id IS NOT NULL
          AND (
              pop.place_id IS NULL
              OR pop.county_id IS NULL
              OR pop.state_id IS NULL
          )
    ) AS incomplete_geography
FROM historical h
LEFT JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = h.raw_award_transaction_id
 AND o.award_transaction_id = h.award_transaction_id
LEFT JOIN procurement.place_of_performance pop
  ON pop.award_transaction_id = h.award_transaction_id
GROUP BY h.load_batch_id
ORDER BY h.load_batch_id;

ROLLBACK;

\echo 'ETL-212T COMPLETE - NO DATABASE WRITES'
