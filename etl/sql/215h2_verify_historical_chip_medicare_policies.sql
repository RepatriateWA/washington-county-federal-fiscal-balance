
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215H2 - HISTORICAL CHIP / MEDICARE CERTIFICATION'
\echo 'ANALYSIS-215H-v1 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. INDEPENDENT POLICY CERTIFICATION'

DO $verify$
DECLARE
    v_version CONSTANT text := 'ANALYSIS-215H-v1';
    v_bad bigint;
    v_count bigint;
    v_amount numeric;
BEGIN
    -- Exactly five new records, in the expected layers.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = v_version;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION 'FAIL: source policy count %', v_bad;
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = v_version;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION 'FAIL: mapping count %', v_bad;
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE methodology_version = v_version;

    IF v_bad <> 3 THEN
        RAISE EXCEPTION 'FAIL: award classification count %', v_bad;
    END IF;

    -- Exact new CHIP classification identities.
    WITH expected(award_id, disposition, subfamily) AS (
        VALUES
        ('1805WA5021', 'EXCLUDE_DUPLICATE',
         'CORE_STATE_T21_FINANCING'),
        ('1905WA5021', 'EXCLUDE_DUPLICATE',
         'CORE_STATE_T21_FINANCING'),
        ('1Y1CMS331701', 'WITHHOLD_UNRESOLVED',
         'HEALTHY_KIDS_TOGETHER')
    ),
    actual AS (
        SELECT
            source_award_identifier AS award_id,
            accounting_disposition AS disposition,
            inflow_subfamily AS subfamily
        FROM reference.federal_inflow_award_classification
        WHERE methodology_version = v_version
          AND source_system = 'USASPENDING_ASSISTANCE'
          AND source_program_code = '93.767'
          AND inflow_family = 'CHIP'
          AND valid_from_fiscal_year = 2018
          AND valid_through_fiscal_year = 2019
    )
    SELECT COUNT(*) INTO v_bad
    FROM (
        (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
        UNION ALL
        (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
    ) differences;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION 'FAIL: CHIP classification mismatch';
    END IF;

    -- New Medicare mapping must point to the new
    -- historical source policy, not the original.
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
      AND s.accounting_measure =
          'ANNUAL_MEDICARE_PAYMENT_STREAMS'
      AND s.preferred_source = 'CMS_NATIVE_MEDICARE'
      AND s.allocation_source = 'CMS_NATIVE_MEDICARE'
      AND s.ledger_treatment = 'EXCLUDE_DUPLICATE'
      AND s.valid_from_fiscal_year = 2018
      AND s.valid_through_fiscal_year = 2019;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION 'FAIL: Medicare policy linkage';
    END IF;

    -- Original FY2020-FY2024 policies still exist.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 6
      AND federal_inflow_source_policy_id = 8
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.770'
      AND resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND methodology_version = 'ANALYSIS-174B-5L-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION 'FAIL: original Medicare mapping';
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE federal_inflow_award_classification_id = 7
      AND source_award_identifier = '1Y1CMS331701'
      AND accounting_disposition = 'WITHHOLD_UNRESOLVED'
      AND methodology_version = 'ANALYSIS-174B-4D-CHIP-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION 'FAIL: original Healthy Kids policy';
    END IF;

    -- All 32 historical transactions remain unchanged
    -- in the source ledger.
    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation),0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) IN ('93.767','93.770');

    IF v_count <> 32 OR v_amount <> 791921828.00 THEN
        RAISE EXCEPTION
            'FAIL: source total rows %, amount %',
            v_count, v_amount;
    END IF;

    -- The 11 unclassified CHIP transactions are still
    -- free of award-level or program-level historical
    -- dispositions.
    WITH remainder AS (
        SELECT
            a.action_date_fiscal_year AS fy,
            COALESCE(
                NULLIF(BTRIM(a.award_id_fain), ''),
                NULLIF(BTRIM(a.award_id_uri), '')
            ) AS award_id,
            a.federal_action_obligation AS amount
        FROM analysis.v_certified_assistance_ledger a
        WHERE (
            (a.load_batch_id = 20
             AND a.action_date_fiscal_year = 2018)
            OR
            (a.load_batch_id = 21
             AND a.action_date_fiscal_year = 2019)
        )
        AND BTRIM(a.cfda_number) = '93.767'
        AND COALESCE(
            NULLIF(BTRIM(a.award_id_fain), ''),
            NULLIF(BTRIM(a.award_id_uri), '')
        ) NOT IN (
            '1805WA5021', '1905WA5021', '1Y1CMS331701'
        )
    )
    SELECT COUNT(*), COALESCE(SUM(r.amount), 0)
    INTO v_count, v_amount
    FROM remainder r
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification c
        WHERE c.source_system = 'USASPENDING_ASSISTANCE'
          AND c.source_program_code = '93.767'
          AND c.source_award_identifier = r.award_id
          AND (c.valid_from_fiscal_year IS NULL
               OR c.valid_from_fiscal_year <= r.fy)
          AND (c.valid_through_fiscal_year IS NULL
               OR c.valid_through_fiscal_year >= r.fy)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = '93.767'
          AND (m.valid_from_fiscal_year IS NULL
               OR m.valid_from_fiscal_year <= r.fy)
          AND (m.valid_through_fiscal_year IS NULL
               OR m.valid_through_fiscal_year >= r.fy)
    );

    IF v_count <> 11 OR v_amount <> -19561782.00 THEN
        RAISE EXCEPTION
            'FAIL: unresolved CHIP rows %, amount %',
            v_count, v_amount;
    END IF;

    RAISE NOTICE 'ETL-215H2 INDEPENDENT CERTIFICATION PASS';
    RAISE NOTICE 'Five historical policy records verified';
    RAISE NOTICE '32 source transactions / $791921828 verified';
    RAISE NOTICE '11 unresolved CHIP transactions preserved';
END
$verify$;

\echo ''
\echo '2. NEW POLICY INVENTORY'

SELECT
    source_award_identifier,
    accounting_disposition,
    inflow_subfamily,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_award_classification
WHERE methodology_version = 'ANALYSIS-215H-v1'
ORDER BY source_award_identifier;

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_program_code,
    m.resolved_accounting_disposition,
    s.federal_inflow_source_policy_id,
    s.preferred_source,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.methodology_version = 'ANALYSIS-215H-v1';

ROLLBACK;

\echo ''
\echo 'ETL-215H2 COMPLETE - READ ONLY'
