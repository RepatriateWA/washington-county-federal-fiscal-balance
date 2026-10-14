-- ============================================================
-- WCFFBP ETL-209Y
-- SNAP AL 10.551 HISTORICAL CONTINUITY / OVERLAP AUDIT
-- FY2018-FY2024
--
-- READ ONLY - NO DATABASE WRITES
-- NO ACCOUNTING POLICY CHANGE
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-209Y - SNAP HISTORICAL CONTINUITY AUDIT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ------------------------------------------------------------
-- 1. Seven-year SNAP obligation series
-- ------------------------------------------------------------

\echo ''
\echo '1. SNAP AL 10.551 - FY2018-FY2024 SERIES'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_awards,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(federal_action_obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '10.551'
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
    OR action_date_fiscal_year BETWEEN 2020 AND 2024
  )
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;


-- ------------------------------------------------------------
-- 2. Award identifier continuity
-- ------------------------------------------------------------

\echo ''
\echo '2. SNAP AWARD IDENTIFIER CONTINUITY'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), ''),
        '[MISSING]'
    ) AS award_identifier,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '10.551'
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
    OR action_date_fiscal_year BETWEEN 2020 AND 2024
  )
GROUP BY 1, 2
ORDER BY fiscal_year, net_obligations DESC;


-- ------------------------------------------------------------
-- 3. Historical FY2018-FY2019 detail
-- ------------------------------------------------------------

\echo ''
\echo '3. HISTORICAL SNAP TRANSACTION DETAIL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    assistance_transaction_id,
    assistance_award_unique_key,
    COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), ''),
        '[MISSING]'
    ) AS award_identifier,
    federal_action_obligation AS obligation
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '10.551'
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
ORDER BY fiscal_year, award_identifier,
         assistance_transaction_id;


-- ------------------------------------------------------------
-- 4. Existing SNAP accounting policy inventory
-- ------------------------------------------------------------

\echo ''
\echo '4. EXISTING SNAP ACCOUNTING POLICY'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.methodology_version,
    m.resolved_accounting_disposition,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.preferred_source,
    p.allocation_source,
    p.accounting_measure,
    p.ledger_treatment,
    p.source_selection_basis
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '10.551'
ORDER BY m.valid_from_fiscal_year;


-- ------------------------------------------------------------
-- 5. Possible SNAP-related policy overlap
-- ------------------------------------------------------------

\echo ''
\echo '5. SNAP-RELATED SOURCE POLICY INVENTORY'

SELECT
    federal_inflow_source_policy_id,
    methodology_version,
    preferred_source,
    allocation_source,
    accounting_measure,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE
    preferred_source ILIKE '%SNAP%'
 OR allocation_source ILIKE '%SNAP%'
 OR source_selection_basis ILIKE '%SNAP%'
 OR source_selection_basis ILIKE '%FOOD STAMP%'
 OR source_selection_basis ILIKE '%FNS-388%'
ORDER BY valid_from_fiscal_year,
         federal_inflow_source_policy_id;


-- ------------------------------------------------------------
-- 6. SNAP / nutrition policy mappings
-- ------------------------------------------------------------

\echo ''
\echo '6. NUTRITION PROGRAM POLICY INVENTORY'

SELECT
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND (
       source_program_code LIKE '10.55%'
    OR source_program_code = '10.561'
  )
ORDER BY source_program_code,
         valid_from_fiscal_year;


-- ------------------------------------------------------------
-- 7. Available recipient / geography / description fields
-- ------------------------------------------------------------

\echo ''
\echo '7. CERTIFIED LEDGER FIELD INVENTORY'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
  AND table_name = 'v_certified_assistance_ledger'
  AND (
       column_name ILIKE '%recipient%'
    OR column_name ILIKE '%description%'
    OR column_name ILIKE '%place%'
    OR column_name ILIKE '%county%'
    OR column_name ILIKE '%state%'
    OR column_name ILIKE '%agency%'
    OR column_name ILIKE '%award%'
    OR column_name ILIKE '%covid%'
  )
ORDER BY ordinal_position;


-- ------------------------------------------------------------
-- 8. Candidate raw / canonical source tables
-- ------------------------------------------------------------

\echo ''
\echo '8. ASSISTANCE SOURCE TABLE INVENTORY'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'assistance'
  AND (
       table_name ILIKE '%award%'
    OR table_name ILIKE '%transaction%'
    OR table_name ILIKE '%recipient%'
    OR table_name ILIKE '%place%'
  )
ORDER BY table_name;


-- ------------------------------------------------------------
-- 9. Historical hard controls
-- ------------------------------------------------------------

\echo ''
\echo '9. HISTORICAL SOURCE CONTROLS'

DO $$
DECLARE
    v_count bigint;
    v_distinct bigint;
    v_net numeric;
    v_gross numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(SUM(ABS(federal_action_obligation)), 0)
    INTO
        v_count,
        v_distinct,
        v_net,
        v_gross
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    IF v_count <> 27
       OR v_distinct <> 27
       OR ROUND(v_net, 2) <> 2461253053.11
       OR ROUND(v_gross, 2) <> 2461808693.93
    THEN
        RAISE EXCEPTION
            'ETL-209Y historical SNAP control failure: rows %, distinct %, net %, gross %',
            v_count, v_distinct, v_net, v_gross;
    END IF;

    RAISE NOTICE
        'ETL-209Y HISTORICAL CONTROL PASS: 27 transactions, $2461253053.11 net obligations';
END $$;

COMMIT;

\echo 'ETL-209Y COMPLETE - READ ONLY'