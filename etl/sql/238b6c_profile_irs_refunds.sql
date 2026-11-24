\pset pager off
\set ON_ERROR_STOP on

\echo 'ETL-238B6C — IRS REFUND PROFILE'
\echo 'READ ONLY — NO DATABASE WRITES'

BEGIN;
SET TRANSACTION READ ONLY;

SELECT
    fiscal_year,
    tax_category,
    gross_collections_thousands,
    refunds_issued,
    refund_amount_thousands,
    CASE
        WHEN gross_collections_thousands IS NOT NULL
         AND refund_amount_thousands IS NOT NULL
        THEN gross_collections_thousands
             - refund_amount_thousands
        ELSE NULL
    END AS candidate_net_collections_thousands,
    source_file
FROM irs.state_collections
WHERE state_name = 'Washington'
  AND fiscal_year BETWEEN 2018 AND 2024
  AND tax_category = 'Total'
ORDER BY fiscal_year;

ROLLBACK;

\echo 'ETL-238B6C COMPLETE — READ ONLY'