
-- WCFFBP ETL-204C-2C.9
-- FY2018-FY2019 RRB 8051 FINAL PROVENANCE GUARD
-- READ ONLY

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

WITH target AS (
    SELECT
        v.action_date_fiscal_year AS fiscal_year,
        v.assistance_transaction_id,
        v.assistance_award_unique_key,
        v.canonical_award_description,
        v.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger v
    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
      AND substring(
          v.assistance_award_unique_key
          FROM '^ASST_AGG_RRB_[0-9]{6}_[[:space:]"]*([0-9]{4})[[:space:]"]*_'
      ) = '8051'
),
evidence AS (
    SELECT
        t.*,
        r.raw_record::text AS raw_text
    FROM target t
    LEFT JOIN assistance.award_transaction_observation o
      ON o.assistance_transaction_id =
         t.assistance_transaction_id
    LEFT JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         o.raw_assistance_transaction_id
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE raw_text ~* '8051[.]001'
    ) AS benefit_subaccount_mentions,
    COUNT(*) FILTER (
        WHERE raw_text ~* '8051[.]002'
    ) AS administrative_subaccount_mentions,
    COUNT(*) FILTER (
        WHERE raw_text ~* 'UNEMPLOYMENT|SICKNESS|BENEFIT CLAIMANT'
    ) AS raw_benefit_text_mentions,
    COUNT(*) FILTER (
        WHERE raw_text IS NULL
    ) AS missing_raw_evidence
FROM evidence
GROUP BY fiscal_year
ORDER BY fiscal_year;

COMMIT;

SELECT 'ETL-204C-2C.9 COMPLETE - NO DATABASE WRITES';
