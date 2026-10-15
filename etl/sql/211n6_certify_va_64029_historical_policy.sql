
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211N6 - HISTORICAL PURCHASE CARE CERTIFICATION'
\echo 'AL 64.029 / FY2018-FY2019'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. COMMITTED POLICY RECORD COUNTS'

SELECT
    'classification' AS record_type,
    COUNT(*) AS records
FROM reference.federal_inflow_program_classification
WHERE methodology_version = 'ANALYSIS-211N-v1'

UNION ALL

SELECT
    'source_policy',
    COUNT(*)
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-211N-v1'

UNION ALL

SELECT
    'program_mapping',
    COUNT(*)
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-211N-v1';

\echo ''
\echo '2. COMMITTED HISTORICAL POLICY RESOLUTION'

SELECT
    m.source_system,
    m.source_program_code,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.resolved_accounting_disposition,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    s.accounting_measure
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.methodology_version = 'ANALYSIS-211N-v1';

\echo ''
\echo '3. CERTIFIED HISTORICAL TRANSACTION POPULATION'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE transaction_description IS NULL
    ) AS missing_descriptions,
    COUNT(*) FILTER (
        WHERE is_covid IS TRUE
    ) AS covid_transactions
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '64.029'
  AND (
      (load_batch_id = 20
       AND action_date_fiscal_year = 2018)
      OR
      (load_batch_id = 21
       AND action_date_fiscal_year = 2019)
  )
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '4. LATER-YEAR POLICY PRESERVATION'

SELECT
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.resolved_accounting_disposition,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    COUNT(*) AS mappings
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '64.029'
GROUP BY
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.resolved_accounting_disposition,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment
ORDER BY m.valid_from_fiscal_year;

\echo ''
\echo '5. INDEPENDENT ASSERTIONS'

DO $$
DECLARE
    v_count bigint;
    v_valid bigint;
    v_2018_count bigint;
    v_2019_count bigint;
    v_2018_amount numeric;
    v_2019_amount numeric;
    v_missing bigint;
BEGIN
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_classification
         WHERE methodology_version = 'ANALYSIS-211N-v1')
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = 'ANALYSIS-211N-v1')
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = 'ANALYSIS-211N-v1')
    INTO v_count;

    IF v_count <> 3 THEN
        RAISE EXCEPTION
            'FAIL: expected 3 committed policy records, found %',
            v_count;
    END IF;

    SELECT COUNT(*)
    INTO v_valid
    FROM reference.federal_inflow_program_classification c
    JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = c.source_system
     AND m.source_program_code = c.source_program_code
     AND m.methodology_version = c.methodology_version
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE c.methodology_version = 'ANALYSIS-211N-v1'
      AND c.source_system = 'USASPENDING_ASSISTANCE'
      AND c.source_program_code = '64.029'
      AND c.overlap_risk = 'KNOWN_OVERLAP'
      AND c.valid_from_fiscal_year = 2018
      AND c.valid_through_fiscal_year = 2019
      AND m.valid_from_fiscal_year = 2018
      AND m.valid_through_fiscal_year = 2019
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND s.methodology_version = 'ANALYSIS-211N-v1'
      AND s.valid_from_fiscal_year = 2018
      AND s.valid_through_fiscal_year = 2019
      AND s.preferred_source = 'VA_GDX'
      AND s.allocation_source = 'VA_GDX'
      AND s.ledger_treatment = 'EXCLUDE_DUPLICATE';

    IF v_valid <> 1 THEN
        RAISE EXCEPTION
            'FAIL: historical policy resolution count %',
            v_valid;
    END IF;

    SELECT
        COUNT(*) FILTER (
            WHERE action_date_fiscal_year = 2018
        ),
        COUNT(*) FILTER (
            WHERE action_date_fiscal_year = 2019
        ),
        COALESCE(SUM(federal_action_obligation) FILTER (
            WHERE action_date_fiscal_year = 2018
        ), 0),
        COALESCE(SUM(federal_action_obligation) FILTER (
            WHERE action_date_fiscal_year = 2019
        ), 0),
        COUNT(*) FILTER (
            WHERE action_date_fiscal_year = 2018
              AND transaction_description IS NULL
        )
    INTO
        v_2018_count,
        v_2019_count,
        v_2018_amount,
        v_2019_amount,
        v_missing
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '64.029'
      AND (
          (load_batch_id = 20
           AND action_date_fiscal_year = 2018)
          OR
          (load_batch_id = 21
           AND action_date_fiscal_year = 2019)
      );

    IF v_2018_count <> 468
       OR v_2019_count <> 468
       OR v_2018_amount <> 152247509
       OR v_2019_amount <> 164889075
       OR v_missing <> 273 THEN
        RAISE EXCEPTION
            'FAIL: historical transaction controls changed';
    END IF;

    SELECT COUNT(*)
    INTO v_valid
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '64.029'
      AND m.methodology_version = 'ANALYSIS-174B-5N-v1'
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND s.preferred_source = 'VA_GDX'
      AND s.allocation_source = 'VA_GDX'
      AND s.ledger_treatment = 'EXCLUDE_DUPLICATE';

    IF v_valid <> 1 THEN
        RAISE EXCEPTION
            'FAIL: later-year policy precedent missing';
    END IF;

    RAISE NOTICE
        'ETL-211N6 ALL ASSERTIONS PASS';
END
$$;

ROLLBACK;

\echo ''
\echo 'ETL-211N6 COMPLETE - NO DATABASE WRITES'
