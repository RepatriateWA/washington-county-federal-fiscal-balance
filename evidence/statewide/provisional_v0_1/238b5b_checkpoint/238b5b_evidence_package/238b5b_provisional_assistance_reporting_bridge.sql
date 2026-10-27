-- ETL-238B5B | Evidence-qualified provisional WA assistance reporting bridge
-- Transaction policy semantics: ETL-236G / ETL-238B5A
-- Reporting scenario only; NO canonical ledger authorization.
-- FY2018-2019 no provisional tags identified: zero is not proof of completeness.
\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION READ ONLY;
\echo 'ETL-238B5B | Annual reporting bridge | USD'
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
),
annual AS (
 SELECT fiscal_year,
 COUNT(*) AS certified_transaction_count,
 COUNT(*) FILTER (WHERE reconciliation_status = 'ALREADY_INCLUDED') AS established_transaction_count,
 COUNT(*) FILTER (WHERE reconciliation_status = 'PROVISIONAL_CANDIDATE') AS provisional_transaction_count,
 COUNT(*) FILTER (WHERE reconciliation_status = 'POLICY_CONFLICT_REVIEW') AS conflict_transaction_count,
 ROUND(COALESCE(SUM(federal_action_obligation) FILTER (WHERE reconciliation_status = 'ALREADY_INCLUDED'),0)::numeric,2) AS established_additive_usd,
 ROUND(COALESCE(SUM(federal_action_obligation) FILTER (WHERE reconciliation_status = 'PROVISIONAL_CANDIDATE'),0)::numeric,2) AS qualified_provisional_usd,
 ROUND(COALESCE(SUM(federal_action_obligation) FILTER (WHERE reconciliation_status = 'PROVISIONAL_CANDIDATE' AND tag_priority = 'IIJA'),0)::numeric,2) AS provisional_iija_usd,
 ROUND(COALESCE(SUM(federal_action_obligation) FILTER (WHERE reconciliation_status = 'PROVISIONAL_CANDIDATE' AND tag_priority = 'COVID'),0)::numeric,2) AS provisional_covid_usd,
 ROUND(COALESCE(SUM(federal_action_obligation) FILTER (WHERE reconciliation_status = 'PROVISIONAL_CANDIDATE' AND tag_priority = 'EXTRAORDINARY'),0)::numeric,2) AS provisional_extraordinary_usd,
 ROUND(COALESCE(SUM(federal_action_obligation),0)::numeric,2) AS certified_universe_usd,
 ROUND(COALESCE(SUM(federal_action_obligation) FILTER (WHERE reconciliation_status NOT IN ('ALREADY_INCLUDED','PROVISIONAL_CANDIDATE')),0)::numeric,2) AS other_dispositions_usd
 FROM bridge GROUP BY fiscal_year
)
SELECT fiscal_year, certified_transaction_count, established_transaction_count,
 provisional_transaction_count, conflict_transaction_count,
 established_additive_usd, qualified_provisional_usd,
 established_additive_usd + qualified_provisional_usd AS expanded_provisional_usd,
 provisional_iija_usd, provisional_covid_usd, provisional_extraordinary_usd,
 qualified_provisional_usd - (provisional_iija_usd + provisional_covid_usd + provisional_extraordinary_usd) AS tag_bucket_difference_usd,
 certified_universe_usd - (established_additive_usd + qualified_provisional_usd + other_dispositions_usd) AS universe_difference_usd
FROM annual ORDER BY fiscal_year;
\echo 'CHECKS: tag_bucket_difference_usd and universe_difference_usd must be zero for each year.'
\echo 'CONTROL: FY2020-FY2024 qualified_provisional_usd sum must equal 9103367430.02.'
\echo 'No database writes; reporting scenario only.'
ROLLBACK;
