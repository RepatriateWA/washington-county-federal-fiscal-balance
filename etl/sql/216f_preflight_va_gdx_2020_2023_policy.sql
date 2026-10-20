
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-216F - VA GDX FY2020-FY2023 POLICY PREFLIGHT'
\echo 'READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. REQUIRED OBJECTS'

DO $verify$
DECLARE
    v_missing text;
BEGIN
    WITH required(schema_name, object_name) AS (
        VALUES
        ('reference','federal_inflow_source_policy'),
        ('va','v_washington_county_gdx_control_total'),
        ('va','gdx_county_expenditure'),
        ('va','gdx_county_metric'),
        ('va','gdx_expenditure_category')
    )
    SELECT string_agg(
        format('%I.%I', schema_name, object_name), ', '
    )
    INTO v_missing
    FROM required
    WHERE to_regclass(
        format('%I.%I', schema_name, object_name)
    ) IS NULL;

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION
            'BLOCK: missing required objects: %', v_missing;
    END IF;

    RAISE NOTICE 'REQUIRED OBJECTS PASS';
END
$verify$;

\echo ''
\echo '2. VA GDX FOUR-YEAR STATEWIDE CONTROLS'

SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT county_id) AS distinct_counties,
    COUNT(*) FILTER (
        WHERE va_gdx_expenditure_amount IS NULL
    ) AS null_amount_rows,
    SUM(va_gdx_expenditure_amount) AS statewide_dollars
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2020 AND 2023
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '3. EXISTING TOTAL VA SOURCE POLICIES'

SELECT
    federal_inflow_source_policy_id,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'VETERANS_AFFAIRS'
  AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
ORDER BY valid_from_fiscal_year, methodology_version;

\echo ''
\echo '4. POLICY AND GEOGRAPHY GATE'

DO $verify$
DECLARE
    v_bad bigint;
    v_count bigint;
    v_amount numeric;
BEGIN
    -- No existing total-VA policy may cover any target year.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_source_policy s
    WHERE s.inflow_family = 'VETERANS_AFFAIRS'
      AND s.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND (
          s.valid_from_fiscal_year IS NULL
          OR s.valid_from_fiscal_year <= 2023
      )
      AND (
          s.valid_through_fiscal_year IS NULL
          OR s.valid_through_fiscal_year >= 2020
      );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % total VA policies overlap FY2020-FY2023',
            v_bad;
    END IF;

    -- Require the exact historical precedent.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND accounting_measure = 'ANNUAL_EXPENDITURES'
      AND preferred_source = 'VA_GDX'
      AND allocation_source = 'VA_GDX'
      AND ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION'
      AND methodology_version = 'ANALYSIS-213-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION
            'BLOCK: historical VA policy precedent count %',
            v_bad;
    END IF;

    -- Require the exact FY2024 precedent.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND accounting_measure = 'ANNUAL_EXPENDITURES'
      AND preferred_source = 'VA_GDX'
      AND allocation_source = 'VA_GDX'
      AND ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION'
      AND methodology_version = 'ANALYSIS-149-v1'
      AND valid_from_fiscal_year = 2024
      AND valid_through_fiscal_year = 2024;

    IF v_bad <> 1 THEN
        RAISE EXCEPTION
            'BLOCK: FY2024 VA policy precedent count %',
            v_bad;
    END IF;

    -- Four years, each with 39 unique county observations.
    WITH per_year AS (
        SELECT
            fiscal_year,
            COUNT(*) AS rows,
            COUNT(DISTINCT county_id) AS counties,
            COUNT(*) FILTER (
                WHERE county_id IS NULL
                   OR va_gdx_expenditure_amount IS NULL
            ) AS null_rows,
            SUM(va_gdx_expenditure_amount) AS dollars
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2020 AND 2023
        GROUP BY fiscal_year
    )
    SELECT COUNT(*) INTO v_bad
    FROM per_year
    WHERE rows = 39
      AND counties = 39
      AND null_rows = 0
      AND dollars > 0;

    IF v_bad <> 4 THEN
        RAISE EXCEPTION
            'BLOCK: only % of four VA GDX years pass',
            v_bad;
    END IF;

    -- Independent known statewide controls from ETL-216D.
    WITH expected(fiscal_year, dollars) AS (
        VALUES
        (2020,5296544030.00::numeric),
        (2021,5323281703.03::numeric),
        (2022,6218866293.72::numeric),
        (2023,6526168355.17::numeric)
    ),
    actual AS (
        SELECT
            fiscal_year,
            SUM(va_gdx_expenditure_amount) AS dollars
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2020 AND 2023
        GROUP BY fiscal_year
    )
    SELECT COUNT(*) INTO v_bad
    FROM (
        (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
        UNION ALL
        (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
    ) differences;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: VA GDX statewide totals differ from ETL-216D';
    END IF;

    -- The proposed version must not already exist.
    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-216F-v1';

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: proposed policy version already exists';
    END IF;

    RAISE NOTICE 'ETL-216F POLICY AND GEOGRAPHY GATE PASS';
END
$verify$;

\echo ''
\echo '5. EXISTING VA OVERLAP POLICIES - PRESERVATION BASELINE'

SELECT
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'VETERANS_AFFAIRS'
  AND inflow_subfamily <> 'TOTAL_VA_EXPENDITURES'
  AND (
      valid_from_fiscal_year IS NULL
      OR valid_from_fiscal_year <= 2023
  )
  AND (
      valid_through_fiscal_year IS NULL
      OR valid_through_fiscal_year >= 2020
  )
ORDER BY inflow_subfamily, methodology_version;

ROLLBACK;

\echo ''
\echo 'ETL-216F PREFLIGHT COMPLETE - READ ONLY'
