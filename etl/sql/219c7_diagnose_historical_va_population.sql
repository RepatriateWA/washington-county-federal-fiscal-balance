
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-219C7 - HISTORICAL VA ASSISTANCE POPULATION'
\echo 'FY2018-FY2019 / READ ONLY'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo '1. HISTORICAL LOAD BATCHES AND GEOGRAPHY'

SELECT
    action_date_fiscal_year AS fiscal_year,
    load_batch_id,
    COALESCE(reference_state_abbreviation, '[NULL]')
        AS reference_state,
    COUNT(*) AS transactions,
    COUNT(DISTINCT cfda_number) AS programs,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year IN (2018,2019)
  AND BTRIM(cfda_number) LIKE '64.%'
GROUP BY
    action_date_fiscal_year,
    load_batch_id,
    reference_state_abbreviation
ORDER BY fiscal_year,load_batch_id,reference_state;

\echo '2. HISTORICAL POLICY RESOLUTION WITHOUT STATE FILTER'

WITH population AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        BTRIM(cfda_number) AS program_code,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS obligations
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year IN (2018,2019)
      AND BTRIM(cfda_number) LIKE '64.%'
      AND load_batch_id IN (20,21)
    GROUP BY 1,2
),
resolved AS (
    SELECT
        p.*,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS mapping_count,
        COUNT(DISTINCT m.resolved_accounting_disposition)
            AS disposition_count,
        MIN(m.resolved_accounting_disposition)
            AS disposition
    FROM population p
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND BTRIM(m.source_program_code) = p.program_code
     AND p.fiscal_year BETWEEN
         m.valid_from_fiscal_year
         AND m.valid_through_fiscal_year
    GROUP BY
        p.fiscal_year,p.program_code,
        p.transactions,p.obligations
)
SELECT
    fiscal_year,
    CASE
        WHEN mapping_count = 0 THEN 'UNMAPPED'
        WHEN disposition_count > 1 THEN 'CONFLICTING'
        WHEN mapping_count > 1 THEN 'MULTIPLE_MAPPINGS'
        ELSE disposition
    END AS policy_status,
    COUNT(*) AS program_years,
    SUM(transactions) AS transactions,
    SUM(obligations) AS net_obligations
FROM resolved
GROUP BY fiscal_year,policy_status
ORDER BY fiscal_year,policy_status;

DO $gate$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'BLOCK: transaction not read-only';
    END IF;
    RAISE NOTICE 'ETL-219C7 DIAGNOSTIC COMPLETE';
END
$gate$;

ROLLBACK;
\echo 'ETL-219C7 COMPLETE - READ ONLY'
