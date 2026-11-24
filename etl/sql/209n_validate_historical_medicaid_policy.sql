
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209N - HISTORICAL MEDICAID POLICY VALIDATION'
\echo 'FY2018-FY2019 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. HISTORICAL POLICY RECORDS'

SELECT
    'SOURCE_POLICY' AS policy_layer,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-209M-v1'

UNION ALL

SELECT
    'PROGRAM_CLASSIFICATION',
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE methodology_version = 'ANALYSIS-209M-v1'

UNION ALL

SELECT
    'PROGRAM_MAPPING',
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-209M-v1'

ORDER BY policy_layer;

\echo ''
\echo '2. NEW MEDICAID ACCOUNTING MAPPING'

SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    p.preferred_source,
    p.accounting_measure,
    p.ledger_treatment,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.methodology_version = 'ANALYSIS-209M-v1';

\echo ''
\echo '3. HISTORICAL TRANSACTION-LEVEL POLICY APPLICABILITY'

WITH historical AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '93.778'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      )
),
resolved AS (
    SELECT
        h.*,
        m.federal_inflow_program_policy_mapping_id,
        m.resolved_accounting_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = '93.778'
     AND h.fiscal_year >= COALESCE(m.valid_from_fiscal_year, -9999)
     AND h.fiscal_year <= COALESCE(m.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(federal_inflow_program_policy_mapping_id)
        AS mapped_rows,
    COUNT(*) FILTER (
        WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
    ) AS excluded_duplicate_rows,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(
        COALESCE(SUM(obligation) FILTER (
            WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
        ), 0)::numeric, 2
    ) AS excluded_duplicate_obligations
FROM resolved
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '4. ORIGINAL FY2020-FY2024 MAPPING'

SELECT
    federal_inflow_program_policy_mapping_id,
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE federal_inflow_program_policy_mapping_id = 5;

\echo ''
\echo '5. POLICY-WINDOW COLLISION CHECK'

SELECT
    a.federal_inflow_program_policy_mapping_id AS mapping_a,
    b.federal_inflow_program_policy_mapping_id AS mapping_b,
    a.methodology_version AS methodology_a,
    b.methodology_version AS methodology_b
FROM reference.federal_inflow_program_policy_mapping a
JOIN reference.federal_inflow_program_policy_mapping b
  ON a.federal_inflow_program_policy_mapping_id
     < b.federal_inflow_program_policy_mapping_id
 AND a.source_system = b.source_system
 AND a.source_program_code = b.source_program_code
 AND COALESCE(a.valid_from_fiscal_year, -9999)
     <= COALESCE(b.valid_through_fiscal_year, 9999)
 AND COALESCE(b.valid_from_fiscal_year, -9999)
     <= COALESCE(a.valid_through_fiscal_year, 9999)
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
  AND a.source_program_code = '93.778';

\echo ''
\echo '6. HARD VALIDATION ASSERTIONS'

DO $$
DECLARE
    v_policy_rows bigint;
    v_tx bigint;
    v_distinct bigint;
    v_mapped bigint;
    v_excluded bigint;
    v_amount numeric;
    v_conflicts bigint;
BEGIN
    SELECT
        (SELECT COUNT(*) FROM reference.federal_inflow_source_policy
         WHERE methodology_version = 'ANALYSIS-209M-v1')
      + (SELECT COUNT(*) FROM reference.federal_inflow_program_classification
         WHERE methodology_version = 'ANALYSIS-209M-v1')
      + (SELECT COUNT(*) FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = 'ANALYSIS-209M-v1')
    INTO v_policy_rows;

    IF v_policy_rows <> 3 THEN
        RAISE EXCEPTION
            'ETL-209N expected 3 policy records; found %',
            v_policy_rows;
    END IF;

    WITH resolved AS (
        SELECT
            c.assistance_transaction_id,
            c.federal_action_obligation,
            m.federal_inflow_program_policy_mapping_id,
            m.resolved_accounting_disposition
        FROM analysis.v_certified_assistance_ledger c
        LEFT JOIN reference.federal_inflow_program_policy_mapping m
          ON m.source_system = 'USASPENDING_ASSISTANCE'
         AND m.source_program_code = '93.778'
         AND c.action_date_fiscal_year
             BETWEEN COALESCE(m.valid_from_fiscal_year, -9999)
                 AND COALESCE(m.valid_through_fiscal_year, 9999)
        WHERE BTRIM(c.cfda_number) = '93.778'
          AND (
               (c.load_batch_id = 20 AND c.action_date_fiscal_year = 2018)
            OR (c.load_batch_id = 21 AND c.action_date_fiscal_year = 2019)
          )
    )
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COUNT(federal_inflow_program_policy_mapping_id),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
        ),
        ROUND(SUM(federal_action_obligation)::numeric, 2)
    INTO v_tx, v_distinct, v_mapped, v_excluded, v_amount
    FROM resolved;

    IF v_tx <> 53
       OR v_distinct <> 53
       OR v_mapped <> 53
       OR v_excluded <> 53
       OR v_amount <> 16453706376.00 THEN
        RAISE EXCEPTION
            'ETL-209N bridge failed: rows %, distinct %, mapped %, excluded %, dollars %',
            v_tx, v_distinct, v_mapped, v_excluded, v_amount;
    END IF;

    SELECT COUNT(*) INTO v_conflicts
    FROM reference.federal_inflow_program_policy_mapping a
    JOIN reference.federal_inflow_program_policy_mapping b
      ON a.federal_inflow_program_policy_mapping_id
         < b.federal_inflow_program_policy_mapping_id
     AND a.source_system = b.source_system
     AND a.source_program_code = b.source_program_code
     AND COALESCE(a.valid_from_fiscal_year, -9999)
         <= COALESCE(b.valid_through_fiscal_year, 9999)
     AND COALESCE(b.valid_from_fiscal_year, -9999)
         <= COALESCE(a.valid_through_fiscal_year, 9999)
    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code = '93.778';

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'ETL-209N overlapping Medicaid policy windows: %',
            v_conflicts;
    END IF;

    RAISE NOTICE
        'ETL-209N PASS: 3 policy records, 53 transactions, $16,453,706,376 nonadditive, zero collisions';
END
$$;

ROLLBACK;

\echo 'ETL-209N COMPLETE - NO DATABASE WRITES'
