-- ============================================================
-- WCFFBP ETL-210T
-- HISTORICAL CMS MEDICARE COVERAGE AND ACCOUNTING-BASIS AUDIT
--
-- Purpose:
--   1. Inventory CMS Medicare data coverage, 2018-2025.
--   2. Examine actual source population by year.
--   3. Identify accounting-period differences.
--   4. Inspect Medicare source and reporting structures.
--   5. Preserve existing accounting policies.
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210T - HISTORICAL CMS MEDICARE COVERAGE AUDIT'
\echo 'FY2018-FY2019 POLICY PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. MEDICARE OBJECT INVENTORY
-- ============================================================

\echo ''
\echo '1. CMS MEDICARE OBJECT INVENTORY'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE (
       (table_schema = 'cms'
        AND table_name IN (
            'medicare_core_state_year',
            'medicare_core_county_year',
            'medicare_geographic_payments'
        ))
    OR (table_schema = 'cms_raw'
        AND table_name = 'medicare_geographic_variation')
    OR (table_schema = 'reporting'
        AND table_name IN (
            'v_medicare_expenditures_by_state_year',
            'v_medicare_expenditures_by_county_year'
        ))
)
ORDER BY table_schema, table_name;


-- ============================================================
-- 2. FULL COLUMN INVENTORY
-- ============================================================

\echo ''
\echo '2. CMS MEDICARE COLUMN INVENTORY'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE (
       (table_schema = 'cms'
        AND table_name IN (
            'medicare_core_state_year',
            'medicare_core_county_year',
            'medicare_geographic_payments'
        ))
    OR (table_schema = 'cms_raw'
        AND table_name = 'medicare_geographic_variation')
    OR (table_schema = 'reporting'
        AND table_name IN (
            'v_medicare_expenditures_by_state_year',
            'v_medicare_expenditures_by_county_year'
        ))
)
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


-- ============================================================
-- 3. HISTORICAL MEDICARE ROW COVERAGE
-- ============================================================

\echo ''
\echo '3. CMS MEDICARE OBSERVATIONS BY YEAR'
\echo 'NOTE: Counts include all stored geographies.'
\echo 'A later section identifies available geography fields.'

DO $$
DECLARE
    v_schema text;
    v_table text;
    v_year_column text;
    v_sql text;
    v_result record;
BEGIN
    FOR v_schema, v_table, v_year_column IN
        SELECT
            c.table_schema,
            c.table_name,
            c.column_name
        FROM information_schema.columns c
        WHERE (
               (c.table_schema = 'cms'
                AND c.table_name IN (
                    'medicare_core_state_year',
                    'medicare_core_county_year',
                    'medicare_geographic_payments'
                ))
            OR (c.table_schema = 'cms_raw'
                AND c.table_name =
                    'medicare_geographic_variation')
            OR (c.table_schema = 'reporting'
                AND c.table_name IN (
                    'v_medicare_expenditures_by_state_year',
                    'v_medicare_expenditures_by_county_year'
                ))
        )
          AND c.column_name IN (
              'calendar_year',
              'report_year',
              'fiscal_year'
          )
        ORDER BY
            c.table_schema,
            c.table_name,
            c.column_name
    LOOP

        RAISE NOTICE
            'SOURCE %.% | YEAR FIELD %',
            v_schema, v_table, v_year_column;

        v_sql := format(
            'SELECT %I::text AS observation_year,
                    COUNT(*)::bigint AS row_count
             FROM %I.%I
             WHERE %I BETWEEN 2018 AND 2025
             GROUP BY %I
             ORDER BY %I',
            v_year_column,
            v_schema,
            v_table,
            v_year_column,
            v_year_column,
            v_year_column
        );

        FOR v_result IN EXECUTE v_sql LOOP
            RAISE NOTICE
                '  YEAR % | ROWS %',
                v_result.observation_year,
                v_result.row_count;
        END LOOP;

    END LOOP;
END $$;


-- ============================================================
-- 4. GEOGRAPHY COLUMN DISCOVERY
-- ============================================================

\echo ''
\echo '4. MEDICARE GEOGRAPHY FIELDS'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE (
       (table_schema = 'cms'
        AND table_name ILIKE '%medicare%')
    OR (table_schema = 'cms_raw'
        AND table_name ILIKE '%medicare%')
    OR (table_schema = 'reporting'
        AND table_name ILIKE '%medicare%')
)
  AND (
       column_name ILIKE '%state%'
    OR column_name ILIKE '%county%'
    OR column_name ILIKE '%fips%'
    OR column_name ILIKE '%geo%'
  )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


-- ============================================================
-- 5. MEDICARE FINANCIAL MEASURE INVENTORY
-- ============================================================

\echo ''
\echo '5. MEDICARE FINANCIAL AND COMPLETENESS FIELDS'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE (
       (table_schema = 'cms'
        AND table_name ILIKE '%medicare%')
    OR (table_schema = 'cms_raw'
        AND table_name ILIKE '%medicare%')
    OR (table_schema = 'reporting'
        AND table_name ILIKE '%medicare%')
)
  AND (
       column_name ILIKE '%payment%'
    OR column_name ILIKE '%expenditure%'
    OR column_name ILIKE '%amount%'
    OR column_name ILIKE '%parta%'
    OR column_name ILIKE '%partb%'
    OR column_name ILIKE '%partc%'
    OR column_name ILIKE '%partd%'
    OR column_name ILIKE '%complete%'
    OR column_name ILIKE '%status%'
    OR column_name ILIKE '%basis%'
  )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


-- ============================================================
-- 6. REPORTING VIEW DEFINITIONS
-- ============================================================

\echo ''
\echo '6. MEDICARE REPORTING VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'reporting'
  AND viewname IN (
      'v_medicare_expenditures_by_state_year',
      'v_medicare_expenditures_by_county_year'
  )
ORDER BY viewname;


-- ============================================================
-- 7. HISTORICAL USASPENDING MEDICARE CONTROL
-- ============================================================

\echo ''
\echo '7. HISTORICAL USASPENDING MEDICARE CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    COUNT(*) AS transactions,
    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) IN ('93.773', '93.774')
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
GROUP BY
    action_date_fiscal_year,
    BTRIM(cfda_number)
ORDER BY
    fiscal_year,
    program_code;


-- ============================================================
-- 8. EXISTING MEDICARE POLICY PERIODS
-- ============================================================

\echo ''
\echo '8. CMS-NATIVE MEDICARE POLICY PERIODS'

SELECT
    federal_inflow_source_policy_id,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    methodology_version
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'MEDICARE'
ORDER BY
    inflow_subfamily,
    valid_from_fiscal_year;


-- ============================================================
-- 9. AUTOMATED SOURCE CONSERVATION
-- ============================================================

\echo ''
\echo '9. AUTOMATED SOURCE CONSERVATION'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_total numeric;
    v_existing_historical_mappings bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )
    INTO
        v_rows,
        v_distinct,
        v_total
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) IN ('93.773', '93.774')
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    SELECT COUNT(*)
    INTO v_existing_historical_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code)
          IN ('93.773', '93.774')
      AND COALESCE(valid_from_fiscal_year, -9999)
          <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999)
          >= 2018;

    IF v_rows <> 36
       OR v_distinct <> 36
       OR ROUND(v_total, 2) <> 2489730308.00
       OR v_existing_historical_mappings <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210T FAIL: rows %, distinct %, total %, historical mappings %',
            v_rows,
            v_distinct,
            v_total,
            v_existing_historical_mappings;
    END IF;

    RAISE NOTICE
        'ETL-210T SOURCE PASS: 36 transactions, $2489730308.00, no historical policy changes';

    RAISE NOTICE
        'CMS COVERAGE CERTIFICATION: PENDING REVIEW OF YEAR, GEOGRAPHY, AND PAYMENT MEASURES';

END $$;

COMMIT;

\echo 'ETL-210T COMPLETE - READ ONLY'