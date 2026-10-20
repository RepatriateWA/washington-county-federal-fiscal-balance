
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-214M2B - HISTORICAL ADDITIVE ASSISTANCE POLICIES'
\echo 'ANALYSIS-214M2B-v1 / FY2018-FY2019'
\echo 'CONTROLLED DATABASE MIGRATION'
\echo '============================================================'

BEGIN;

SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

LOCK TABLE
    reference.federal_inflow_source_policy,
    reference.federal_inflow_program_policy_mapping,
    reference.federal_inflow_program_classification
IN SHARE ROW EXCLUSIVE MODE;

\echo ''
\echo '1. Execute guarded historical policy migration'

DO $migration$
DECLARE
    v_version CONSTANT text := 'ANALYSIS-214M2B-v1';
    v_expected CONSTANT numeric := 3622669747.07;
    v_rows bigint;
    v_amount numeric;
    v_count integer;
    v_max_id bigint;
    v_source_count integer;
    v_mapping_count integer;
    v_class_count integer;
    v_original_count integer;
    v_conflicts integer;
BEGIN
    -- Prevent accidental re-execution.
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
    INTO v_count;

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: migration version already exists (% rows)',
            v_count;
    END IF;

    -- Verify exact historical population and obligations.
    WITH expected(program_code, fiscal_year, tx, amount) AS (
        VALUES
        ('10.555',2018,13,310634787.39::numeric),
        ('10.555',2019,17,305359589.09::numeric),
        ('84.010',2018,10,232545366.00::numeric),
        ('84.010',2019,10,238764152.00::numeric),
        ('84.027',2018,5,232193764.34::numeric),
        ('84.027',2019,7,233532123.91::numeric),
        ('84.063',2018,6665,429174205.04::numeric),
        ('84.063',2019,6382,411678307.30::numeric),
        ('93.558',2018,42,342908453.00::numeric),
        ('93.558',2019,41,437029211.00::numeric),
        ('93.600',2018,297,207088736.00::numeric),
        ('93.600',2019,306,241761052.00::numeric)
    ),
    actual AS (
        SELECT
            TRIM(cfda_number) AS program_code,
            action_date_fiscal_year AS fiscal_year,
            COUNT(*) AS tx,
            SUM(federal_action_obligation) AS amount
        FROM analysis.v_certified_assistance_ledger
        WHERE (
            (load_batch_id = 20 AND action_date_fiscal_year = 2018)
            OR
            (load_batch_id = 21 AND action_date_fiscal_year = 2019)
        )
        AND TRIM(cfda_number) IN (
            '10.555','84.010','84.027',
            '84.063','93.558','93.600'
        )
        GROUP BY 1,2
    )
    SELECT COUNT(*)
    INTO v_conflicts
    FROM (
        SELECT
            COALESCE(e.program_code,a.program_code) AS code,
            COALESCE(e.fiscal_year,a.fiscal_year) AS fy
        FROM expected e
        FULL JOIN actual a
          ON a.program_code=e.program_code
         AND a.fiscal_year=e.fiscal_year
        WHERE e.tx IS DISTINCT FROM a.tx
           OR e.amount IS DISTINCT FROM a.amount
    ) discrepancies;

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % historical program-year control discrepancies',
            v_conflicts;
    END IF;

    SELECT COUNT(*), SUM(federal_action_obligation)
    INTO v_rows, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND TRIM(cfda_number) IN (
        '10.555','84.010','84.027',
        '84.063','93.558','93.600'
    );

    IF v_rows <> 13795 OR v_amount <> v_expected THEN
        RAISE EXCEPTION
            'BLOCK: historical control differs: rows=%, amount=%',
            v_rows, v_amount;
    END IF;

    -- Require exactly one existing 2020-2024 mapping
    -- for each of the six target programs.
    SELECT COUNT(*)
    INTO v_original_count
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      )
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024
      AND s.valid_from_fiscal_year = 2020
      AND s.valid_through_fiscal_year = 2024
      AND m.resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND s.accounting_measure =
          'NET_FEDERAL_ACTION_OBLIGATION'
      AND s.preferred_source = 'USASPENDING_ASSISTANCE'
      AND s.ledger_treatment = 'INCLUDE';

    IF v_original_count <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: expected six original policy mappings; found %',
            v_original_count;
    END IF;

    -- Require exactly one original classification per
    -- program, with no existing historical classification.
    SELECT COUNT(*)
    INTO v_class_count
    FROM reference.federal_inflow_program_classification c
    WHERE c.source_system = 'USASPENDING_ASSISTANCE'
      AND c.source_program_code IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      )
      AND c.valid_from_fiscal_year = 2020
      AND c.valid_through_fiscal_year = 2024
      AND c.overlap_risk = 'NONE';

    IF v_class_count <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: expected six original classifications; found %',
            v_class_count;
    END IF;

    -- Any historical overlap or unbounded validity
    -- interval blocks the migration.
    SELECT COUNT(*)
    INTO v_conflicts
    FROM reference.federal_inflow_program_policy_mapping m
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      )
      AND (
          m.valid_from_fiscal_year IS NULL
          OR m.valid_through_fiscal_year IS NULL
          OR (
              m.valid_from_fiscal_year <= 2019
              AND m.valid_through_fiscal_year >= 2018
          )
      );

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: historical mapping collision count %',
            v_conflicts;
    END IF;

    SELECT COUNT(*)
    INTO v_conflicts
    FROM reference.federal_inflow_program_classification c
    WHERE c.source_system = 'USASPENDING_ASSISTANCE'
      AND c.source_program_code IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      )
      AND (
          c.valid_from_fiscal_year IS NULL
          OR c.valid_through_fiscal_year IS NULL
          OR (
              c.valid_from_fiscal_year <= 2019
              AND c.valid_through_fiscal_year >= 2018
          )
      );

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: historical classification collision count %',
            v_conflicts;
    END IF;

    SELECT COUNT(*)
    INTO v_conflicts
    FROM reference.federal_inflow_source_policy s
    WHERE EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping m
        JOIN reference.federal_inflow_source_policy original
          ON original.federal_inflow_source_policy_id =
             m.federal_inflow_source_policy_id
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code IN (
              '10.555','84.010','84.027',
              '84.063','93.558','93.600'
          )
          AND m.valid_from_fiscal_year = 2020
          AND m.valid_through_fiscal_year = 2024
          AND original.inflow_family = s.inflow_family
          AND original.inflow_subfamily IS NOT DISTINCT FROM
              s.inflow_subfamily
    )
    AND (
        s.valid_from_fiscal_year IS NULL
        OR s.valid_through_fiscal_year IS NULL
        OR (
            s.valid_from_fiscal_year <= 2019
            AND s.valid_through_fiscal_year >= 2018
        )
    );

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: historical source-policy collision count %',
            v_conflicts;
    END IF;

    RAISE NOTICE
        'PRE-MIGRATION PASS: % transactions / $% obligations',
        v_rows, v_amount;

    -- Clone the six source policies without altering
    -- their accounting measure or source-selection fields.
    INSERT INTO reference.federal_inflow_source_policy (
        inflow_family,
        inflow_subfamily,
        accounting_measure,
        preferred_source,
        allocation_source,
        overlapping_sources,
        ledger_treatment,
        source_selection_basis,
        methodology_version,
        valid_from_fiscal_year,
        valid_through_fiscal_year
    )
    SELECT
        s.inflow_family,
        s.inflow_subfamily,
        s.accounting_measure,
        s.preferred_source,
        s.allocation_source,
        s.overlapping_sources,
        s.ledger_treatment,
        'ANALYSIS-214M2B-v1: FY2018-FY2019 historical '
        || 'extension of source policy '
        || s.federal_inflow_source_policy_id::text
        || '. Net federal action obligations, not cash '
        || 'expenditures. Raw historical agency and '
        || 'recipient provenance is preserved; normalized '
        || 'enrichment and county economic incidence '
        || 'remain separately unresolved. '
        || s.source_selection_basis,
        v_version,
        2018,
        2019
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      )
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024;

    GET DIAGNOSTICS v_source_count = ROW_COUNT;

    IF v_source_count <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: inserted % source policies, expected 6',
            v_source_count;
    END IF;

    -- Mapping IDs have no sequence default.
    SELECT COALESCE(MAX(federal_inflow_program_policy_mapping_id),0)
    INTO v_max_id
    FROM reference.federal_inflow_program_policy_mapping;

    INSERT INTO reference.federal_inflow_program_policy_mapping (
        federal_inflow_program_policy_mapping_id,
        source_system,
        source_program_code,
        federal_inflow_source_policy_id,
        resolved_accounting_disposition,
        mapping_basis,
        methodology_version,
        valid_from_fiscal_year,
        valid_through_fiscal_year
    )
    SELECT
        v_max_id + ROW_NUMBER() OVER (
            ORDER BY m.source_program_code
        ),
        m.source_system,
        m.source_program_code,
        historical.federal_inflow_source_policy_id,
        m.resolved_accounting_disposition,
        'ANALYSIS-214M2B-v1: FY2018-FY2019 '
        || 'historical extension of mapping '
        || m.federal_inflow_program_policy_mapping_id::text
        || '. Original FY2020-FY2024 mapping retained. '
        || m.mapping_basis,
        v_version,
        2018,
        2019
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy original
      ON original.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    JOIN reference.federal_inflow_source_policy historical
      ON historical.inflow_family = original.inflow_family
     AND historical.inflow_subfamily IS NOT DISTINCT FROM
         original.inflow_subfamily
     AND historical.methodology_version = v_version
     AND historical.valid_from_fiscal_year = 2018
     AND historical.valid_through_fiscal_year = 2019
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      )
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024;

    GET DIAGNOSTICS v_mapping_count = ROW_COUNT;

    IF v_mapping_count <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: inserted % mappings, expected 6',
            v_mapping_count;
    END IF;

    -- Clone existing program classifications.
    INSERT INTO reference.federal_inflow_program_classification (
        source_system,
        source_program_code,
        source_program_title,
        inflow_family,
        inflow_subfamily,
        overlap_risk,
        covid_relevance,
        extraordinary_relevance,
        classification_basis,
        methodology_version,
        valid_from_fiscal_year,
        valid_through_fiscal_year
    )
    SELECT
        c.source_system,
        c.source_program_code,
        c.source_program_title,
        c.inflow_family,
        c.inflow_subfamily,
        c.overlap_risk,
        c.covid_relevance,
        c.extraordinary_relevance,
        'ANALYSIS-214M2B-v1: FY2018-FY2019 '
        || 'historical extension. Original classification '
        || c.federal_inflow_program_classification_id::text
        || ' retained. ' || c.classification_basis,
        v_version,
        2018,
        2019
    FROM reference.federal_inflow_program_classification c
    WHERE c.source_system = 'USASPENDING_ASSISTANCE'
      AND c.source_program_code IN (
          '10.555','84.010','84.027',
          '84.063','93.558','93.600'
      )
      AND c.valid_from_fiscal_year = 2020
      AND c.valid_through_fiscal_year = 2024
      AND c.overlap_risk = 'NONE';

    GET DIAGNOSTICS v_class_count = ROW_COUNT;

    IF v_class_count <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: inserted % classifications, expected 6',
            v_class_count;
    END IF;

    -- Confirm every new mapping points to its matching
    -- new source policy and retains the accounting rules.
    SELECT COUNT(*)
    INTO v_count
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
      AND m.valid_from_fiscal_year = 2018
      AND m.valid_through_fiscal_year = 2019
      AND s.valid_from_fiscal_year = 2018
      AND s.valid_through_fiscal_year = 2019
      AND c.valid_from_fiscal_year = 2018
      AND c.valid_through_fiscal_year = 2019
      AND c.inflow_family = s.inflow_family
      AND c.inflow_subfamily IS NOT DISTINCT FROM
          s.inflow_subfamily
      AND m.resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND s.accounting_measure =
          'NET_FEDERAL_ACTION_OBLIGATION'
      AND s.preferred_source = 'USASPENDING_ASSISTANCE'
      AND s.ledger_treatment = 'INCLUDE'
      AND c.overlap_risk = 'NONE';

    IF v_count <> 6 THEN
        RAISE EXCEPTION
            'POST-MIGRATION FAILURE: valid joined policies=%',
            v_count;
    END IF;

    RAISE NOTICE
        'POST-MIGRATION PASS: source=%, mapping=%, classification=%',
        v_source_count, v_mapping_count, v_class_count;
    RAISE NOTICE
        'Historical control: % transactions / $%',
        v_rows, v_amount;
END
$migration$;

\echo ''
\echo '2. New historical mappings and source policies'

SELECT
    m.source_program_code,
    m.federal_inflow_program_policy_mapping_id AS mapping_id,
    s.federal_inflow_source_policy_id AS source_policy_id,
    s.inflow_family,
    s.inflow_subfamily,
    m.resolved_accounting_disposition,
    s.accounting_measure,
    s.preferred_source,
    s.allocation_source,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.methodology_version
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.methodology_version = 'ANALYSIS-214M2B-v1'
ORDER BY m.source_program_code;

\echo ''
\echo '3. New policy row counts'

SELECT 'source_policy' AS policy_table, COUNT(*) AS rows
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-214M2B-v1'
UNION ALL
SELECT 'program_mapping', COUNT(*)
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-214M2B-v1'
UNION ALL
SELECT 'program_classification', COUNT(*)
FROM reference.federal_inflow_program_classification
WHERE methodology_version = 'ANALYSIS-214M2B-v1';

COMMIT;

\echo ''
\echo 'ETL-214M2B COMPLETE - COMMIT ISSUED'
