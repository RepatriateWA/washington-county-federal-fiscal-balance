-- ETL-238B5A | WA assistance provisional restoration diagnostic
-- READ ONLY. No temp tables, persistent writes, or ledger authorizations.
\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION READ ONLY;

-- Classify each certified WA transaction once using the ETL-236G policy semantics.
-- MATERIALIZED CTE prevents repeated expensive evaluation within this statement.
WITH tx AS MATERIALIZED (
 SELECT assistance_transaction_id, action_date_fiscal_year AS fiscal_year,
        cfda_number, assistance_award_unique_key, award_id_fain, award_id_uri,
        federal_action_obligation, is_covid, is_iija, is_extraordinary
 FROM analysis.v_certified_assistance_ledger
 WHERE reference_state_abbreviation = 'WA'
   AND action_date_fiscal_year BETWEEN 2018 AND 2024
),
program_policy AS (
 SELECT t.assistance_transaction_id,
        COUNT(DISTINCT p.resolved_accounting_disposition) AS distinct_dispositions,
        MIN(p.resolved_accounting_disposition) AS disposition
 FROM tx t JOIN reference.federal_inflow_program_policy_mapping p
 ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = t.cfda_number
 AND t.fiscal_year >= COALESCE(p.valid_from_fiscal_year, -2147483648)
 AND t.fiscal_year <= COALESCE(p.valid_through_fiscal_year, 2147483647)
 GROUP BY t.assistance_transaction_id
),
award_policy AS (
 SELECT t.assistance_transaction_id,
        COUNT(DISTINCT a.accounting_disposition) AS distinct_dispositions,
        MIN(a.accounting_disposition) AS disposition
 FROM tx t JOIN reference.federal_inflow_award_classification a
 ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = t.cfda_number
 AND t.fiscal_year >= COALESCE(a.valid_from_fiscal_year, -2147483648)
 AND t.fiscal_year <= COALESCE(a.valid_through_fiscal_year, 2147483647)
 AND a.source_award_identifier IN
     (t.assistance_award_unique_key, t.award_id_fain, t.award_id_uri)
 GROUP BY t.assistance_transaction_id
),
classified AS MATERIALIZED (
 SELECT t.*,
 CASE WHEN a.distinct_dispositions > 1 THEN 'CONFLICTING_AWARD_POLICIES'
      WHEN a.disposition IS NOT NULL THEN a.disposition
      WHEN p.distinct_dispositions > 1 THEN 'CONFLICTING_PROGRAM_POLICIES'
      WHEN p.disposition IS NOT NULL THEN p.disposition
      ELSE 'NO_APPLICABLE_POLICY' END AS current_disposition
 FROM tx t LEFT JOIN award_policy a USING (assistance_transaction_id)
 LEFT JOIN program_policy p USING (assistance_transaction_id)
),
bridge AS (
 SELECT *,
 CASE WHEN current_disposition = 'INCLUDE_ADDITIVE' THEN 'ALREADY_INCLUDED'
      WHEN current_disposition = 'NO_APPLICABLE_POLICY'
       AND (is_iija IS TRUE OR is_covid IS TRUE OR is_extraordinary IS TRUE)
       THEN 'PROVISIONAL_CANDIDATE'
      WHEN current_disposition = 'NO_APPLICABLE_POLICY' THEN 'UNRESOLVED_ORDINARY'
      WHEN current_disposition LIKE 'CONFLICTING_%' THEN 'POLICY_CONFLICT_REVIEW'
      ELSE 'POLICY_EXCLUDED_OR_WITHHELD' END AS reconciliation_status,
 CASE WHEN is_iija IS TRUE THEN 'IIJA'
      WHEN is_covid IS TRUE THEN 'COVID'
      WHEN is_extraordinary IS TRUE THEN 'EXTRAORDINARY'
      ELSE 'UNTAGGED' END AS tag_priority
 FROM classified
)
SELECT fiscal_year, reconciliation_status, current_disposition, tag_priority,
 COUNT(*) AS transaction_count,
 ROUND(SUM(federal_action_obligation)::numeric,2) AS net_obligation_usd
FROM bridge
GROUP BY fiscal_year, reconciliation_status, current_disposition, tag_priority
ORDER BY fiscal_year, reconciliation_status, current_disposition, tag_priority;

ROLLBACK;
