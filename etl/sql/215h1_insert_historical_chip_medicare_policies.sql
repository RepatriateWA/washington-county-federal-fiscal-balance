
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215H1 - HISTORICAL CHIP / MEDICARE POLICIES'
\echo 'ANALYSIS-215H-v1 / CONTROLLED MIGRATION'
\echo '============================================================'

BEGIN;

SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

LOCK TABLE
    reference.federal_inflow_source_policy,
    reference.federal_inflow_program_policy_mapping,
    reference.federal_inflow_award_classification
IN SHARE ROW EXCLUSIVE MODE;

DO $migration$
DECLARE
    v_version CONSTANT text := 'ANALYSIS-215H-v1';
    v_count bigint;
    v_amount numeric;
    v_bad bigint;
    v_source_id bigint;
    v_mapping_id bigint;
    v_rows bigint;
BEGIN
    -- Idempotence: block rerunning this migration.
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = v_version)
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = v_version)
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_award_classification
         WHERE methodology_version = v_version)
    INTO v_bad;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: methodology version already exists: % rows',
            v_bad;
    END IF;

    -- Four exact historical program/year source controls.
    WITH expected(fy, code, tx, amount) AS (
        VALUES
        (2018, '93.767', 9::bigint, 259213635.00::numeric),
        (2019, '93.767', 7::bigint, 217211867.00::numeric),
        (2018, '93.770', 8::bigint, 190442657.00::numeric),
        (2019, '93.770', 8::bigint, 125053669.00::numeric)
    ),
    actual AS (
        SELECT
            action_date_fiscal_year AS fy,
            BTRIM(cfda_number) AS code,
            COUNT(*) AS tx,
            SUM(federal_action_obligation) AS amount
        FROM analysis.v_certified_assistance_ledger
        WHERE (
            (load_batch_id = 20 AND action_date_fiscal_year = 2018)
            OR
            (load_batch_id = 21 AND action_date_fiscal_year = 2019)
        )
        AND BTRIM(cfda_number) IN ('93.767', '93.770')
        GROUP BY 1, 2
    )
    SELECT COUNT(*) INTO v_bad
    FROM expected e
    FULL JOIN actual a USING (fy, code)
    WHERE e.tx IS DISTINCT FROM a.tx
       OR e.amount IS DISTINCT FROM a.amount;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: historical source controls differ (% groups)',
            v_bad;
    END IF;

    -- Exact award-level accounting controls.
    WITH expected(award_id, tx, amount) AS (
        VALUES
        ('1805WA5021', 2::bigint, 259290773.00::numeric),
        ('1905WA5021', 2::bigint, 236312742.00::numeric),
        ('1Y1CMS331701', 1::bigint, 383769.00::numeric)
    ),
    actual AS (
        SELECT
            BTRIM(award_id_fain) AS award_id,
            COUNT(*) AS tx,
            SUM(federal_action_obligation) AS amount
        FROM analysis.v_certified_assistance_ledger
        WHERE (
            (load_batch_id = 20 AND action_date_fiscal_year = 2018)
            OR
            (load_batch_id = 21 AND action_date_fiscal_year = 2019)
        )
        AND BTRIM(cfda_number) = '93.767'
        AND BTRIM(award_id_fain) IN (
            '1805WA5021',
            '1905WA5021',
            '1Y1CMS331701'
        )
        GROUP BY 1
    )
    SELECT COUNT(*) INTO v_bad
    FROM expected e
    FULL JOIN actual a USING (award_id)
    WHERE e.tx IS DISTINCT FROM a.tx
       OR e.amount IS DISTINCT FROM a.amount;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: target CHIP award controls differ';
    END IF;

    -- Exact unresolved remainder: preserve all 11 rows.
    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.767'
    AND COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), '')
    ) NOT IN (
        '1805WA5021',
        '1905WA5021',
        '1Y1CMS331701'
    );

    IF v_count <> 11 OR v_amount <> -19561782.00 THEN
        RAISE EXCEPTION
            'BLOCK: unresolved CHIP remainder differs';
    END IF;

    -- Confirm the original source hierarchy and mapping.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '93.770'
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024
      AND s.inflow_family = 'MEDICARE'
      AND s.inflow_subfamily = 'PRESCRIPTION_DRUG_COVERAGE'
      AND s.accounting_measure =
          'ANNUAL_MEDICARE_PAYMENT_STREAMS'
      AND s.preferred_source = 'CMS_NATIVE_MEDICARE'
      AND s.allocation_source = 'CMS_NATIVE_MEDICARE'
      AND s.ledger_treatment = 'EXCLUDE_DUPLICATE'
      AND s.valid_from_fiscal_year = 2020
      AND s.valid_through_fiscal_year = 2024;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION
            'BLOCK: expected one original Medicare policy';
    END IF;

    -- Verify the original CHIP award precedents.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND (
          (
              source_award_identifier IN (
                  '2005WA5021', '2105WA5021',
                  '2205WA5021', '2305WA5021',
                  '2405WA5021'
              )
              AND inflow_family = 'CHIP'
              AND inflow_subfamily =
                  'CORE_STATE_T21_FINANCING'
              AND accounting_disposition =
                  'EXCLUDE_DUPLICATE'
          )
          OR (
              source_award_identifier = '1Y1CMS331701'
              AND inflow_family = 'CHIP'
              AND inflow_subfamily =
                  'HEALTHY_KIDS_TOGETHER'
              AND accounting_disposition =
                  'WITHHOLD_UNRESOLVED'
          )
      )
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_bad <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: original CHIP precedents differ';
    END IF;

    -- No historical or unbounded policy collisions.
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE source_system = 'USASPENDING_ASSISTANCE'
           AND source_program_code = '93.770'
           AND (
               valid_from_fiscal_year IS NULL
               OR valid_through_fiscal_year IS NULL
               OR (
                   valid_from_fiscal_year <= 2019
                   AND valid_through_fiscal_year >= 2018
               )
           ))
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_award_classification
         WHERE source_system = 'USASPENDING_ASSISTANCE'
           AND source_program_code = '93.767'
           AND source_award_identifier IN (
               '1805WA5021',
               '1905WA5021',
               '1Y1CMS331701'
           )
           AND (
               valid_from_fiscal_year IS NULL
               OR valid_through_fiscal_year IS NULL
               OR (
                   valid_from_fiscal_year <= 2019
                   AND valid_through_fiscal_year >= 2018
               )
           ))
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE inflow_family = 'MEDICARE'
           AND inflow_subfamily = 'PRESCRIPTION_DRUG_COVERAGE'
           AND (
               valid_from_fiscal_year IS NULL
               OR valid_through_fiscal_year IS NULL
               OR (
                   valid_from_fiscal_year <= 2019
                   AND valid_through_fiscal_year >= 2018
               )
           ))
    INTO v_bad;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: historical policy collision count %',
            v_bad;
    END IF;

    RAISE NOTICE 'PRE-MIGRATION CONTROLS PASS';

    -- Create a historical Medicare source policy by
    -- cloning the established source-selection fields.
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
        'ANALYSIS-215H-v1: Historical FY2018-FY2019 '
        || 'extension of source policy '
        || s.federal_inflow_source_policy_id::text
        || '. USAspending 93.770 obligations are '
        || 'reconciliation evidence, not a second '
        || 'additive Medicare payment stream. '
        || 'CMS calendar-year timing, Part D partial '
        || 'coverage, and principal-ledger authorization '
        || 'remain separately unresolved. '
        || s.source_selection_basis,
        v_version,
        2018,
        2019
    FROM reference.federal_inflow_source_policy s
    WHERE s.federal_inflow_source_policy_id = 8
      AND s.inflow_family = 'MEDICARE'
      AND s.inflow_subfamily = 'PRESCRIPTION_DRUG_COVERAGE'
      AND s.valid_from_fiscal_year = 2020
      AND s.valid_through_fiscal_year = 2024
    RETURNING federal_inflow_source_policy_id
    INTO v_source_id;

    IF v_source_id IS NULL THEN
        RAISE EXCEPTION 'BLOCK: Medicare source insert failed';
    END IF;

    -- Mapping table has no identity/default.
    -- The table lock protects explicit MAX(id)+1 allocation.
    SELECT COALESCE(
        MAX(federal_inflow_program_policy_mapping_id), 0
    ) + 1
    INTO v_mapping_id
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
    VALUES (
        v_mapping_id,
        'USASPENDING_ASSISTANCE',
        '93.770',
        v_source_id,
        'EXCLUDE_DUPLICATE',
        'ANALYSIS-215H-v1: Historical FY2018-FY2019 '
        || 'extension of Medicare Part D program mapping '
        || '6. All 16 historical transactions follow '
        || 'quarterly aggregate-style reporting patterns. '
        || 'Net obligations $315,496,326.00. '
        || 'No FFY cash-expenditure equivalence asserted.',
        v_version,
        2018,
        2019
    );

    -- Award-specific CHIP classifications.
    INSERT INTO reference.federal_inflow_award_classification (
        source_system,
        source_program_code,
        source_award_identifier,
        inflow_family,
        inflow_subfamily,
        accounting_disposition,
        classification_basis,
        methodology_version,
        valid_from_fiscal_year,
        valid_through_fiscal_year
    )
    VALUES
    (
        'USASPENDING_ASSISTANCE',
        '93.767',
        '1805WA5021',
        'CHIP',
        'CORE_STATE_T21_FINANCING',
        'EXCLUDE_DUPLICATE',
        'ANALYSIS-215H-v1: FY2018 state T21 '
        || 'financing pattern. Two transactions, '
        || '$259,290,773 obligations. CMS-native '
        || 'CHIP actual expenditures are the preferred '
        || 'accounting path. Historical recipient '
        || 'names are unavailable in the observation '
        || 'view. This is program-stream overlap, '
        || 'not dollar-for-dollar reconciliation.',
        v_version, 2018, 2019
    ),
    (
        'USASPENDING_ASSISTANCE',
        '93.767',
        '1905WA5021',
        'CHIP',
        'CORE_STATE_T21_FINANCING',
        'EXCLUDE_DUPLICATE',
        'ANALYSIS-215H-v1: FY2019 state T21 '
        || 'financing pattern. Two transactions, '
        || '$236,312,742 obligations. CMS-native '
        || 'CHIP expenditures are preferred. '
        || 'Recipient-name evidence remains '
        || 'unresolved; the classification rests '
        || 'on award structure and earlier policy.',
        v_version, 2018, 2019
    ),
    (
        'USASPENDING_ASSISTANCE',
        '93.767',
        '1Y1CMS331701',
        'CHIP',
        'HEALTHY_KIDS_TOGETHER',
        'WITHHOLD_UNRESOLVED',
        'ANALYSIS-215H-v1: FY2019 historical '
        || 'extension of award classification 7. '
        || 'One transaction, $383,769 obligations. '
        || 'Distinct from core T21 award structure; '
        || 'independent additivity is not established.',
        v_version, 2018, 2019
    );

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows <> 3 THEN
        RAISE EXCEPTION
            'BLOCK: inserted % CHIP classifications, expected 3',
            v_rows;
    END IF;

    -- Final structural and accounting verification.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE methodology_version = v_version
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    IF v_bad <> 3 THEN
        RAISE EXCEPTION
            'BLOCK: CHIP post-insert count %', v_bad;
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.methodology_version = v_version
      AND s.methodology_version = v_version
      AND m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '93.770'
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND m.valid_from_fiscal_year = 2018
      AND m.valid_through_fiscal_year = 2019
      AND s.inflow_family = 'MEDICARE'
      AND s.inflow_subfamily = 'PRESCRIPTION_DRUG_COVERAGE'
      AND s.preferred_source = 'CMS_NATIVE_MEDICARE'
      AND s.ledger_treatment = 'EXCLUDE_DUPLICATE'
      AND s.valid_from_fiscal_year = 2018
      AND s.valid_through_fiscal_year = 2019;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION
            'BLOCK: Medicare post-insert verification failed';
    END IF;

    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = v_version)
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = v_version)
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_award_classification
         WHERE methodology_version = v_version)
    INTO v_bad;

    IF v_bad <> 5 THEN
        RAISE EXCEPTION
            'BLOCK: expected five new records, found %',
            v_bad;
    END IF;

    RAISE NOTICE
        'POST-MIGRATION PASS: 1 source, 1 mapping, 3 awards';
    RAISE NOTICE
        'Historical dispositions: 21 transactions, $811483610';
    RAISE NOTICE
        'Unmapped CHIP preserved: 11 transactions, -$19561782';
END
$migration$;

\echo ''
\echo 'NEW HISTORICAL POLICY RECORDS'

SELECT
    'SOURCE_POLICY' AS policy_layer,
    federal_inflow_source_policy_id AS record_id,
    inflow_subfamily AS subject,
    ledger_treatment AS disposition
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-215H-v1'

UNION ALL

SELECT
    'PROGRAM_MAPPING',
    federal_inflow_program_policy_mapping_id,
    source_program_code,
    resolved_accounting_disposition
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-215H-v1'

UNION ALL

SELECT
    'AWARD_CLASSIFICATION',
    federal_inflow_award_classification_id,
    source_award_identifier,
    accounting_disposition
FROM reference.federal_inflow_award_classification
WHERE methodology_version = 'ANALYSIS-215H-v1'
ORDER BY policy_layer, subject;

COMMIT;

\echo ''
\echo 'ETL-215H1 COMPLETE - MIGRATION COMMITTED'
