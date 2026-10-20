
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215I3C - HISTORICAL CHIP RESIDUAL CERTIFICATION'
\echo 'ANALYSIS-215I3-v1 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. INDEPENDENT CERTIFICATION CONTROLS'

DO $verify$
DECLARE
    v_bad bigint;
    v_count bigint;
    v_amount numeric;
BEGIN
    -- Exactly six records in the new version, all
    -- confined to the award-classification layer.
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_award_classification
         WHERE methodology_version = 'ANALYSIS-215I3-v1')
    INTO v_count;

    IF v_count <> 6 THEN
        RAISE EXCEPTION
            'FAIL: expected six award records, found %',
            v_count;
    END IF;

    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = 'ANALYSIS-215I3-v1')
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = 'ANALYSIS-215I3-v1')
    INTO v_bad;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'FAIL: unexpected source policies or mappings';
    END IF;

    -- Compare every expected classification with
    -- committed records, including dates and disposition.
    WITH expected(award_id, subfamily, disposition) AS (
        VALUES
        ('1805WA5R21',
         'CORE_T21_REVERSAL',
         'EXCLUDE_DUPLICATE'),
        ('0905WACPBP',
         'HISTORICAL_PERFORMANCE_BONUS_ADJUSTMENT',
         'WITHHOLD_UNRESOLVED'),
        ('1005WACPBP',
         'HISTORICAL_PERFORMANCE_BONUS_ADJUSTMENT',
         'WITHHOLD_UNRESOLVED'),
        ('1105WACPBP',
         'HISTORICAL_PERFORMANCE_BONUS_ADJUSTMENT',
         'WITHHOLD_UNRESOLVED'),
        ('1205WACPBP',
         'HISTORICAL_PERFORMANCE_BONUS_ADJUSTMENT',
         'WITHHOLD_UNRESOLVED'),
        ('1Z0CMS330855',
         'OUTREACH_ENROLLMENT_CORRECTION',
         'WITHHOLD_UNRESOLVED')
    ),
    actual AS (
        SELECT
            source_award_identifier AS award_id,
            inflow_subfamily AS subfamily,
            accounting_disposition AS disposition
        FROM reference.federal_inflow_award_classification
        WHERE methodology_version = 'ANALYSIS-215I3-v1'
          AND source_system = 'USASPENDING_ASSISTANCE'
          AND source_program_code = '93.767'
          AND inflow_family = 'CHIP'
          AND valid_from_fiscal_year = 2018
          AND valid_through_fiscal_year = 2019
          AND NULLIF(BTRIM(classification_basis), '')
              IS NOT NULL
    )
    SELECT COUNT(*) INTO v_bad
    FROM expected e
    FULL JOIN actual a USING (award_id)
    WHERE e.subfamily IS DISTINCT FROM a.subfamily
       OR e.disposition IS DISTINCT FROM a.disposition;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'FAIL: % award classification discrepancies',
            v_bad;
    END IF;

    -- Independently reconcile the transaction population.
    WITH expected(award_id, tx, amount) AS (
        VALUES
        ('1805WA5R21',   6::bigint,         0::numeric),
        ('0905WACPBP',   1::bigint,  -5136424::numeric),
        ('1005WACPBP',   1::bigint,  -6553366::numeric),
        ('1105WACPBP',   1::bigint,  -2916476::numeric),
        ('1205WACPBP',   1::bigint,  -4878378::numeric),
        ('1Z0CMS330855', 1::bigint,    -77138::numeric)
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
              '1805WA5R21',
              '0905WACPBP', '1005WACPBP',
              '1105WACPBP', '1205WACPBP',
              '1Z0CMS330855'
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
            'FAIL: underlying transaction totals differ';
    END IF;

    -- Preserve the three ETL-215H historical CHIP records.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE methodology_version = 'ANALYSIS-215H-v1'
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019
      AND (
          (source_award_identifier = '1805WA5021'
           AND accounting_disposition = 'EXCLUDE_DUPLICATE')
          OR
          (source_award_identifier = '1905WA5021'
           AND accounting_disposition = 'EXCLUDE_DUPLICATE')
          OR
          (source_award_identifier = '1Y1CMS331701'
           AND accounting_disposition = 'WITHHOLD_UNRESOLVED')
      );

    IF v_bad <> 3 THEN
        RAISE EXCEPTION
            'FAIL: historical CHIP precedents differ';
    END IF;

    -- Preserve the historical Medicare Part D mapping.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.methodology_version = 'ANALYSIS-215H-v1'
      AND s.methodology_version = 'ANALYSIS-215H-v1'
      AND m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '93.770'
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND m.valid_from_fiscal_year = 2018
      AND m.valid_through_fiscal_year = 2019
      AND s.inflow_family = 'MEDICARE'
      AND s.inflow_subfamily = 'PRESCRIPTION_DRUG_COVERAGE'
      AND s.preferred_source = 'CMS_NATIVE_MEDICARE';

    IF v_bad <> 1 THEN
        RAISE EXCEPTION
            'FAIL: historical Medicare mapping differs';
    END IF;

    -- Ensure the original FY2020-FY2024 policy remains.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.federal_inflow_program_policy_mapping_id = 6
      AND s.federal_inflow_source_policy_id = 8
      AND m.source_program_code = '93.770'
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024
      AND s.preferred_source = 'CMS_NATIVE_MEDICARE';

    IF v_bad <> 1 THEN
        RAISE EXCEPTION
            'FAIL: original Medicare policy differs';
    END IF;

    -- Confirm no conflicting classifications overlap
    -- the new awards during FY2018-FY2019.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification a
    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code = '93.767'
      AND a.source_award_identifier IN (
          '1805WA5R21', '1Z0CMS330855',
          '0905WACPBP', '1005WACPBP',
          '1105WACPBP', '1205WACPBP'
      )
      AND a.methodology_version <> 'ANALYSIS-215I3-v1'
      AND (
          a.valid_from_fiscal_year IS NULL
          OR a.valid_through_fiscal_year IS NULL
          OR (
              a.valid_from_fiscal_year <= 2019
              AND a.valid_through_fiscal_year >= 2018
          )
      );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'FAIL: % conflicting award policies', v_bad;
    END IF;

    -- Reconcile the full FY2018-FY2019 CHIP population.
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20
         AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21
         AND action_date_fiscal_year = 2019)
    )
      AND BTRIM(cfda_number) = '93.767';

    IF v_count <> 16 OR v_amount <> 476425502 THEN
        RAISE EXCEPTION
            'FAIL: full historical CHIP controls differ';
    END IF;

    RAISE NOTICE 'ETL-215I3C CERTIFICATION PASS';
    RAISE NOTICE
        'Six new award policies / 11 transactions';
    RAISE NOTICE
        'Zero-net reversal excluded; five adjustments withheld';
    RAISE NOTICE
        'Historical CHIP and Medicare precedents preserved';
END
$verify$;

\echo ''
\echo '2. CERTIFIED AWARD ACCOUNTING SUMMARY'

SELECT
    c.inflow_subfamily,
    c.accounting_disposition,
    COUNT(DISTINCT c.source_award_identifier) AS awards,
    COUNT(*) AS transactions,
    SUM(a.federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger a
JOIN reference.federal_inflow_award_classification c
  ON c.source_system = 'USASPENDING_ASSISTANCE'
 AND c.source_program_code = BTRIM(a.cfda_number)
 AND c.source_award_identifier = BTRIM(a.award_id_fain)
 AND c.methodology_version = 'ANALYSIS-215I3-v1'
WHERE (
    (a.load_batch_id = 20
     AND a.action_date_fiscal_year = 2018)
    OR
    (a.load_batch_id = 21
     AND a.action_date_fiscal_year = 2019)
)
  AND BTRIM(a.cfda_number) = '93.767'
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '3. COMMITTED POLICY RECORDS'

SELECT
    federal_inflow_award_classification_id,
    source_award_identifier,
    inflow_subfamily,
    accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_award_classification
WHERE methodology_version = 'ANALYSIS-215I3-v1'
ORDER BY source_award_identifier;

ROLLBACK;

\echo ''
\echo 'ETL-215I3C COMPLETE - READ ONLY'
