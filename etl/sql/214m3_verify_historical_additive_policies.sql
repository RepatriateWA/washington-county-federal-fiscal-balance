
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214M3 - HISTORICAL ADDITIVE POLICY CERTIFICATION'
\echo 'READ ONLY - FY2018-FY2024'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

DO $verify$
DECLARE
    v_version CONSTANT text := 'ANALYSIS-214M2B-v1';
    v_bad integer;
    v_rows bigint;
    v_amount numeric;
    v_policies integer;
BEGIN
    -- All three historical policy layers must contain
    -- exactly six records.
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = v_version)
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = v_version)
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_program_classification
         WHERE methodology_version = v_version)
    INTO v_policies;

    IF v_policies <> 18 THEN
        RAISE EXCEPTION
            'FAIL: expected 18 historical policy records; got %',
            v_policies;
    END IF;

    -- Confirm six unique, correctly joined historical
    -- program policies with no altered accounting measure.
    SELECT COUNT(*)
    INTO v_bad
    FROM (
        SELECT
            m.source_program_code,
            COUNT(*) AS matches
        FROM reference.federal_inflow_program_policy_mapping m
        JOIN reference.federal_inflow_source_policy s
          ON s.federal_inflow_source_policy_id =
             m.federal_inflow_source_policy_id
        JOIN reference.federal_inflow_program_classification c
          ON c.source_system = m.source_system
         AND c.source_program_code = m.source_program_code
         AND c.methodology_version = v_version
        WHERE m.methodology_version = v_version
          AND s.methodology_version = v_version
          AND m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.valid_from_fiscal_year = 2018
          AND m.valid_through_fiscal_year = 2019
          AND s.valid_from_fiscal_year = 2018
          AND s.valid_through_fiscal_year = 2019
          AND c.valid_from_fiscal_year = 2018
          AND c.valid_through_fiscal_year = 2019
          AND m.resolved_accounting_disposition =
              'INCLUDE_ADDITIVE'
          AND s.accounting_measure =
              'NET_FEDERAL_ACTION_OBLIGATION'
          AND s.preferred_source = 'USASPENDING_ASSISTANCE'
          AND s.ledger_treatment = 'INCLUDE'
          AND c.overlap_risk = 'NONE'
          AND c.inflow_family = s.inflow_family
          AND c.inflow_subfamily IS NOT DISTINCT FROM
              s.inflow_subfamily
        GROUP BY m.source_program_code
    ) q
    WHERE q.matches <> 1;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'FAIL: % historical program policy multiplicities',
            v_bad;
    END IF;

    SELECT COUNT(*)
    INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = v_version
      AND source_program_code NOT IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'FAIL: unexpected historical program codes';
    END IF;

    -- Confirm original FY2020-FY2024 mappings
    -- remain present under their original identifiers.
    SELECT COUNT(*)
    INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping
    WHERE (
        source_program_code,
        federal_inflow_program_policy_mapping_id,
        federal_inflow_source_policy_id
    ) IN (
        ('10.555',82,35),
        ('84.010',75,26),
        ('84.027',73,27),
        ('84.063',74,25),
        ('93.558',81,34),
        ('93.600',84,39)
    )
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';

    IF v_bad <> 6 THEN
        RAISE EXCEPTION
            'FAIL: original mapping baseline count=%',
            v_bad;
    END IF;

    -- Recompute source transaction controls.
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation),0)
    INTO v_rows, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
      AND TRIM(cfda_number) IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      );

    IF v_rows <> 13795
       OR v_amount <> 3622669747.07 THEN
        RAISE EXCEPTION
            'FAIL: historical transactions=% obligations=%',
            v_rows, v_amount;
    END IF;

    RAISE NOTICE
        'ETL-214M3 PASS: 18 historical policy records';
    RAISE NOTICE
        'ETL-214M3 PASS: six original mappings retained';
    RAISE NOTICE
        'ETL-214M3 PASS: % transactions / $% obligations',
        v_rows, v_amount;
END
$verify$;

\echo ''
\echo 'HISTORICAL PROGRAM-YEAR ACCOUNTING CONTROLS'

SELECT
    TRIM(cfda_number) AS program_code,
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE (
    (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND TRIM(cfda_number) IN (
    '10.555','84.010','84.027',
    '84.063','93.558','93.600'
)
GROUP BY 1,2
ORDER BY 1,2;

ROLLBACK;

\echo 'ETL-214M3 COMPLETE - READ ONLY'
