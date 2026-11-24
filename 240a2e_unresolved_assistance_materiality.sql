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
)
SELECT
    COALESCE(cfda_number, '[NULL]') AS assistance_listing,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS seven_year_net_usd,
    ROUND(SUM(ABS(federal_action_obligation))::numeric, 2)
        AS seven_year_absolute_activity_usd,
    ROUND(COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE fiscal_year = 2018), 0)::numeric, 2)
        AS fy2018_usd,
    ROUND(COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE fiscal_year = 2019), 0)::numeric, 2)
        AS fy2019_usd,
    ROUND(COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE fiscal_year = 2020), 0)::numeric, 2)
        AS fy2020_usd,
    ROUND(COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE fiscal_year = 2021), 0)::numeric, 2)
        AS fy2021_usd,
    ROUND(COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE fiscal_year = 2022), 0)::numeric, 2)
        AS fy2022_usd,
    ROUND(COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE fiscal_year = 2023), 0)::numeric, 2)
        AS fy2023_usd,
    ROUND(COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE fiscal_year = 2024), 0)::numeric, 2)
        AS fy2024_usd
FROM bridge
WHERE reconciliation_status = 'UNRESOLVED_ORDINARY'
GROUP BY cfda_number
ORDER BY ABS(SUM(federal_action_obligation)) DESC
LIMIT 40;

ROLLBACK;
