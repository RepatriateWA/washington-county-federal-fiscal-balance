-- ============================================================
-- WCFFBP ETL-209X
-- SNAP AL 10.551 HISTORICAL SOURCE AND OVERLAP PROFILE
-- FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- NO LEDGER INCLUSION OR EXCLUSION DECISION
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-209X - HISTORICAL SNAP AL 10.551 PROFILE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ------------------------------------------------------------
-- 1. Source controls
-- ------------------------------------------------------------

\echo ''
\echo '1. SNAP SOURCE CONTROLS BY FISCAL YEAR'

WITH snap AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
          (load_batch_id = 20
           AND action_date_fiscal_year = 2018)
          OR
          (load_batch_id = 21
           AND action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT award_identifier)
        AS distinct_awards,
    COUNT(*) FILTER (WHERE obligation > 0)
        AS positive_transactions,
    COUNT(*) FILTER (WHERE obligation < 0)
        AS negative_transactions,
    COUNT(*) FILTER (WHERE obligation = 0)
        AS zero_transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM snap
GROUP BY fiscal_year
ORDER BY fiscal_year;


-- ------------------------------------------------------------
-- 2. Award-level detail
-- ------------------------------------------------------------

\echo ''
\echo '2. SNAP AWARD IDENTIFIER PROFILE'

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
      OR
      (load_batch_id = 21
       AND action_date_fiscal_year = 2019)
  )
GROUP BY 1, 2
ORDER BY fiscal_year, net_obligations DESC;


-- ------------------------------------------------------------
-- 3. Existing program classifications
-- ------------------------------------------------------------

\echo ''
\echo '3. EXISTING SNAP PROGRAM CLASSIFICATIONS'

SELECT
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    classification_basis
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '10.551'
ORDER BY valid_from_fiscal_year, methodology_version;


-- ------------------------------------------------------------
-- 4. Existing program-level accounting policies
-- ------------------------------------------------------------

\echo ''
\echo '4. EXISTING SNAP PROGRAM POLICY MAPPINGS'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment,
    p.accounting_measure,
    p.source_selection_basis
FROM reference.federal_inflow_program_policy_mapping m
LEFT JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '10.551'
ORDER BY m.valid_from_fiscal_year, m.methodology_version;


-- ------------------------------------------------------------
-- 5. Award-level classifications
-- ------------------------------------------------------------

\echo ''
\echo '5. SNAP AWARD CLASSIFICATION INVENTORY'

SELECT
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS classification_rows
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '10.551'
GROUP BY 1, 2, 3, 4
ORDER BY 3, 2, 1;


-- ------------------------------------------------------------
-- 6. Effective accounting resolution
-- Uses ETL-209Q/209W precedence:
-- award > program > unclassified
-- ------------------------------------------------------------

\echo ''
\echo '6. EFFECTIVE SNAP ACCOUNTING RESOLUTION'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE BTRIM(c.cfda_number) = '10.551'
      AND (
          (c.load_batch_id = 20
           AND c.action_date_fiscal_year = 2018)
          OR
          (c.load_batch_id = 21
           AND c.action_date_fiscal_year = 2019)
      )
),
resolved AS (
    SELECT
        h.*,
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    COALESCE(
        award_disposition,
        program_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE award_disposition IS NOT NULL
          AND program_disposition IS NOT NULL
    ) AS award_program_collisions
FROM resolved
GROUP BY 1, 2
ORDER BY 1, 2;


-- ------------------------------------------------------------
-- 7. Hard source controls
-- ------------------------------------------------------------

\echo ''
\echo '7. AUTOMATED SOURCE CONTROLS'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_amount numeric;
    v_gross numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(SUM(ABS(federal_action_obligation)), 0)
    INTO
        v_rows,
        v_distinct,
        v_amount,
        v_gross
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
          (load_batch_id = 20
           AND action_date_fiscal_year = 2018)
          OR
          (load_batch_id = 21
           AND action_date_fiscal_year = 2019)
      );

    IF v_rows <> 27
       OR v_distinct <> 27
       OR ROUND(v_amount, 2) <> 2461253053.11
       OR ROUND(v_gross, 2) <> 2461808693.93
    THEN
        RAISE EXCEPTION
            'ETL-209X SOURCE CONTROL FAILURE: rows %, distinct %, net %, gross %',
            v_rows, v_distinct, v_amount, v_gross;
    END IF;

    RAISE NOTICE
        'ETL-209X SOURCE CONTROL PASS: 27 transactions, $2461253053.11 net obligations';
END $$;

COMMIT;

\echo 'ETL-209X COMPLETE - READ ONLY'