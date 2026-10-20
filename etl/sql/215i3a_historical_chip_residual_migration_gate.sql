
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215I3A - HISTORICAL CHIP RESIDUAL MIGRATION GATE'
\echo 'ANALYSIS-215I3-v1 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

DO $gate$
DECLARE
    v_bad bigint;
    v_count bigint;
    v_amount numeric;
BEGIN
    -- Previous historical policy must remain intact.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE methodology_version = 'ANALYSIS-215H-v1'
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND source_award_identifier IN (
          '1805WA5021', '1905WA5021', '1Y1CMS331701'
      )
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    IF v_bad <> 3 THEN
        RAISE EXCEPTION 'BLOCK: ETL-215H CHIP baseline differs';
    END IF;

    -- Six award controls: full outer join detects missing
    -- awards as well as unexpected counts or amounts.
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
        RAISE EXCEPTION 'BLOCK: award accounting controls differ';
    END IF;

    -- Check the entire historical CHIP population.
    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation),0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
      AND BTRIM(cfda_number) = '93.767';

    IF v_count <> 16 OR v_amount <> 476425502 THEN
        RAISE EXCEPTION
            'BLOCK: full CHIP population differs: % / %',
            v_count, v_amount;
    END IF;

    -- Every target transaction must link to exactly
    -- one immutable raw observation.
    WITH target AS (
        SELECT assistance_transaction_id
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
    ),
    counts AS (
        SELECT
            t.assistance_transaction_id,
            COUNT(r.raw_assistance_transaction_id) AS raw_count
        FROM target t
        LEFT JOIN assistance.award_transaction_observation o
          ON o.assistance_transaction_id =
             t.assistance_transaction_id
        LEFT JOIN assistance.raw_award_transaction r
          ON r.raw_assistance_transaction_id =
             o.raw_assistance_transaction_id
        GROUP BY 1
    )
    SELECT COUNT(*) INTO v_bad
    FROM counts
    WHERE raw_count <> 1;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % transactions lack unique raw provenance',
            v_bad;
    END IF;

    -- Verify original source descriptions and activity.
    WITH raw AS (
        SELECT
            a.award_id_fain,
            a.assistance_transaction_id,
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
    WHERE raw_record->>'prime_award_transaction_place_of_performance_state_fips_code'
              IS DISTINCT FROM '53'
       OR raw_record->>'cfda_number'
              IS DISTINCT FROM '93.767'
       OR (
           award_id_fain LIKE '%WACPBP'
           AND COALESCE(
               raw_record->>'program_activities_funding_this_award',
               ''
           ) NOT ILIKE '%PERFORMANCE BONUS PAYMENTS%'
       );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % raw source provenance discrepancies',
            v_bad;
    END IF;

    -- Block version reuse and overlapping award policies.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE methodology_version = 'ANALYSIS-215I3-v1';

    IF v_bad <> 0 THEN
        RAISE EXCEPTION 'BLOCK: methodology version exists';
    END IF;

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
            'BLOCK: % overlapping award classifications',
            v_bad;
    END IF;

    RAISE NOTICE
        'ETL-215I3A PRE-MIGRATION GATE PASS';
    RAISE NOTICE
        '11 transactions / 6 awards / -$19561782';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-215I3A COMPLETE - READ ONLY'
