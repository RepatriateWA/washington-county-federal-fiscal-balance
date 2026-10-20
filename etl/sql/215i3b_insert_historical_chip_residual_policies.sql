
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215I3B - HISTORICAL CHIP RESIDUAL POLICIES'
\echo 'ANALYSIS-215I3-v1 / CONTROLLED MIGRATION'
\echo '============================================================'

BEGIN;

SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

LOCK TABLE reference.federal_inflow_award_classification
IN SHARE ROW EXCLUSIVE MODE;

DO $migration$
DECLARE
    v_version CONSTANT text := 'ANALYSIS-215I3-v1';
    v_bad bigint;
    v_rows bigint;
BEGIN
    -- Idempotence across all policy layers.
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_award_classification
         WHERE methodology_version = v_version)
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = v_version)
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = v_version)
    INTO v_bad;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: methodology version already exists';
    END IF;

    -- Recheck the exact six award totals inside
    -- the same transaction that performs the insert.
    WITH expected(award_id, tx, amount) AS (
        VALUES
        ('1805WA5R21',   6::bigint,         0::numeric),
        ('1Z0CMS330855', 1::bigint,    -77138::numeric),
        ('0905WACPBP',   1::bigint,  -5136424::numeric),
        ('1005WACPBP',   1::bigint,  -6553366::numeric),
        ('1105WACPBP',   1::bigint,  -2916476::numeric),
        ('1205WACPBP',   1::bigint,  -4878378::numeric)
    ),
    actual AS (
        SELECT
            BTRIM(award_id_fain) AS award_id,
            COUNT(*) AS tx,
            SUM(federal_action_obligation) AS amount
        FROM analysis.v_certified_assistance_ledger
        WHERE (
            (load_batch_id = 20
             AND action_date_fiscal_year = 2018)
            OR
            (load_batch_id = 21
             AND action_date_fiscal_year = 2019)
        )
          AND BTRIM(cfda_number) = '93.767'
          AND BTRIM(award_id_fain) IN (
              '1805WA5R21', '1Z0CMS330855',
              '0905WACPBP', '1005WACPBP',
              '1105WACPBP', '1205WACPBP'
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
            'BLOCK: historical award controls changed';
    END IF;

    -- Preserve the original ETL-215H classifications.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE methodology_version = 'ANALYSIS-215H-v1'
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND source_award_identifier IN (
          '1805WA5021',
          '1905WA5021',
          '1Y1CMS331701'
      )
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    IF v_bad <> 3 THEN
        RAISE EXCEPTION
            'BLOCK: ETL-215H precedent differs';
    END IF;

    -- No overlapping historical classifications.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND source_award_identifier IN (
          '1805WA5R21', '1Z0CMS330855',
          '0905WACPBP', '1005WACPBP',
          '1105WACPBP', '1205WACPBP'
      )
      AND (
          valid_from_fiscal_year IS NULL
          OR valid_through_fiscal_year IS NULL
          OR (
              valid_from_fiscal_year <= 2019
              AND valid_through_fiscal_year >= 2018
          )
      );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: overlapping award policies found';
    END IF;

    -- Reconfirm source activity evidence.
    WITH raw AS (
        SELECT
            a.award_id_fain,
            r.raw_record
        FROM analysis.v_certified_assistance_ledger a
        JOIN assistance.award_transaction_observation o
          ON o.assistance_transaction_id =
             a.assistance_transaction_id
        JOIN assistance.raw_award_transaction r
          ON r.raw_assistance_transaction_id =
             o.raw_assistance_transaction_id
        WHERE (
            (a.load_batch_id = 20
             AND a.action_date_fiscal_year = 2018)
            OR
            (a.load_batch_id = 21
             AND a.action_date_fiscal_year = 2019)
        )
          AND BTRIM(a.cfda_number) = '93.767'
          AND a.award_id_fain IN (
              '1805WA5R21', '1Z0CMS330855',
              '0905WACPBP', '1005WACPBP',
              '1105WACPBP', '1205WACPBP'
          )
    )
    SELECT COUNT(*) INTO v_bad
    FROM raw
    WHERE raw_record->>'cfda_number'
              IS DISTINCT FROM '93.767'
       OR raw_record->>
          'prime_award_transaction_place_of_performance_state_fips_code'
              IS DISTINCT FROM '53'
       OR (
           award_id_fain LIKE '%WACPBP'
           AND COALESCE(
               raw_record->>'program_activities_funding_this_award',
               ''
           ) NOT ILIKE '%PERFORMANCE BONUS PAYMENTS%'
       );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: raw provenance differs';
    END IF;

    RAISE NOTICE 'PRE-MIGRATION CONTROLS PASS';

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
        '1805WA5R21',
        'CHIP',
        'CORE_T21_REVERSAL',
        'EXCLUDE_DUPLICATE',
        'ANALYSIS-215I3-v1; ETL-215I1/I2B evidence. '
        || 'FY2018 Q1 Title XXI entitlement. '
        || 'Six signed transactions, modifications 0-5, '
        || 'net federal obligations $0. '
        || 'Source correction indicators support '
        || 'an obligation-reversal sequence. '
        || 'CMS-native CHIP expenditures remain preferred. '
        || 'EXCLUDE_DUPLICATE denotes nonadditivity, '
        || 'not proven dollar-for-dollar cash duplication. '
        || 'No independent cash expenditure asserted.',
        v_version, 2018, 2019
    ),
    (
        'USASPENDING_ASSISTANCE',
        '93.767',
        '0905WACPBP',
        'CHIP',
        'HISTORICAL_PERFORMANCE_BONUS_ADJUSTMENT',
        'WITHHOLD_UNRESOLVED',
        'ANALYSIS-215I3-v1; ETL-215I2B raw evidence. '
        || 'CMS program activity 0002 PERFORMANCE BONUS '
        || 'PAYMENTS. FY2019-05-23 negative obligation '
        || '-$5,136,424. Historical cash treatment and '
        || 'CMS CHIP expenditure overlap not established.',
        v_version, 2018, 2019
    ),
    (
        'USASPENDING_ASSISTANCE',
        '93.767',
        '1005WACPBP',
        'CHIP',
        'HISTORICAL_PERFORMANCE_BONUS_ADJUSTMENT',
        'WITHHOLD_UNRESOLVED',
        'ANALYSIS-215I3-v1; ETL-215I2B raw evidence. '
        || 'CMS program activity 0002 PERFORMANCE BONUS '
        || 'PAYMENTS. FY2019-05-23 negative obligation '
        || '-$6,553,366. Historical cash treatment and '
        || 'CMS CHIP expenditure overlap not established.',
        v_version, 2018, 2019
    ),
    (
        'USASPENDING_ASSISTANCE',
        '93.767',
        '1105WACPBP',
        'CHIP',
        'HISTORICAL_PERFORMANCE_BONUS_ADJUSTMENT',
        'WITHHOLD_UNRESOLVED',
        'ANALYSIS-215I3-v1; ETL-215I2B raw evidence. '
        || 'CMS program activity 0002 PERFORMANCE BONUS '
        || 'PAYMENTS. FY2019-05-23 negative obligation '
        || '-$2,916,476. Historical cash treatment and '
        || 'CMS CHIP expenditure overlap not established.',
        v_version, 2018, 2019
    ),
    (
        'USASPENDING_ASSISTANCE',
        '93.767',
        '1205WACPBP',
        'CHIP',
        'HISTORICAL_PERFORMANCE_BONUS_ADJUSTMENT',
        'WITHHOLD_UNRESOLVED',
        'ANALYSIS-215I3-v1; ETL-215I2B raw evidence. '
        || 'CMS program activity 0002 PERFORMANCE BONUS '
        || 'PAYMENTS. FY2019-05-23 negative obligation '
        || '-$4,878,378. Historical cash treatment and '
        || 'CMS CHIP expenditure overlap not established.',
        v_version, 2018, 2019
    ),
    (
        'USASPENDING_ASSISTANCE',
        '93.767',
        '1Z0CMS330855',
        'CHIP',
        'OUTREACH_ENROLLMENT_CORRECTION',
        'WITHHOLD_UNRESOLVED',
        'ANALYSIS-215I3-v1; ETL-215I2B raw evidence. '
        || 'CHIP outreach/enrollment grant correction, '
        || 'negative obligation -$77,138. '
        || 'Original source correction indicator retained. '
        || 'CMS CHIP expenditure overlap and cash treatment '
        || 'not independently established.',
        v_version, 2018, 2019
    );

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: inserted % awards, expected 6',
            v_rows;
    END IF;

    -- Post-insert control.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE methodology_version = v_version
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    IF v_bad <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: post-insert award count differs';
    END IF;

    RAISE NOTICE
        'POST-MIGRATION PASS: six award classifications';
    RAISE NOTICE
        'EXCLUDE_DUPLICATE: 6 transactions, $0';
    RAISE NOTICE
        'WITHHOLD_UNRESOLVED: 5 transactions, -$19561782';
END
$migration$;

\echo ''
\echo 'NEW HISTORICAL CHIP RESIDUAL CLASSIFICATIONS'

SELECT
    federal_inflow_award_classification_id AS classification_id,
    source_award_identifier AS award_id,
    inflow_subfamily,
    accounting_disposition,
    methodology_version
FROM reference.federal_inflow_award_classification
WHERE methodology_version = 'ANALYSIS-215I3-v1'
ORDER BY source_award_identifier;

COMMIT;

\echo ''
\echo 'ETL-215I3B COMPLETE - MIGRATION COMMITTED'
