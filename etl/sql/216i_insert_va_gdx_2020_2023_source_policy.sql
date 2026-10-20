
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-216I - VA GDX FY2020-FY2023 SOURCE POLICY'
\echo 'ANALYSIS-216I-v1 / CONTROLLED MIGRATION'
\echo '======================================================'

BEGIN;
SET LOCAL statement_timeout = '180s';

LOCK TABLE reference.federal_inflow_source_policy
    IN SHARE ROW EXCLUSIVE MODE;

\echo ''
\echo '1. FAIL-CLOSED PRE-MIGRATION ASSERTIONS'

DO $gate$
DECLARE
    v_conflicts bigint;
    v_precedents bigint;
    v_counties bigint;
    v_failures bigint;
BEGIN
    SELECT COUNT(*) INTO v_conflicts
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-216I-v1'
       OR (
           inflow_family = 'VETERANS_AFFAIRS'
           AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
           AND (
               valid_from_fiscal_year IS NULL
               OR valid_from_fiscal_year <= 2023
           )
           AND (
               valid_through_fiscal_year IS NULL
               OR valid_through_fiscal_year >= 2020
           )
       );

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: conflicting or existing policy rows: %',
            v_conflicts;
    END IF;

    SELECT COUNT(*) INTO v_precedents
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND accounting_measure = 'ANNUAL_EXPENDITURES'
      AND preferred_source = 'VA_GDX'
      AND allocation_source = 'VA_GDX'
      AND overlapping_sources =
          ARRAY['USASPENDING_PROCUREMENT']::text[]
      AND ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION'
      AND (
          (
              methodology_version = 'ANALYSIS-213-v1'
              AND valid_from_fiscal_year = 2018
              AND valid_through_fiscal_year = 2019
          )
          OR
          (
              methodology_version = 'ANALYSIS-149-v1'
              AND valid_from_fiscal_year = 2024
              AND valid_through_fiscal_year = 2024
          )
      );

    IF v_precedents <> 2 THEN
        RAISE EXCEPTION
            'BLOCK: expected two source-policy precedents; found %',
            v_precedents;
    END IF;

    WITH county AS (
        SELECT
            e.fiscal_year,
            e.county_id,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS component_rows,
            COUNT(DISTINCT c.category_code) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS component_categories,
            COUNT(*) FILTER (
                WHERE c.category_code = 'TOTAL_EXPENDITURE'
                  AND c.aggregation_role = 'CONTROL_TOTAL'
            ) AS control_rows,
            COUNT(*) FILTER (
                WHERE e.expenditure_amount IS NULL
            ) AS null_rows,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS components,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.category_code = 'TOTAL_EXPENDITURE'
                  AND c.aggregation_role = 'CONTROL_TOTAL'
            ) AS control
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2020 AND 2023
        GROUP BY e.fiscal_year, e.county_id
    )
    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE component_rows <> 7
               OR component_categories <> 7
               OR control_rows <> 1
               OR null_rows <> 0
               OR components IS NULL
               OR control IS NULL
               OR components <> control
        )
    INTO v_counties, v_failures
    FROM county;

    IF v_counties <> 156 OR v_failures <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: county observations %, failures %',
            v_counties, v_failures;
    END IF;

    RAISE NOTICE
        'PRE-MIGRATION CONTROLS PASS';
END
$gate$;

\echo ''
\echo '2. INSERT FY2020-FY2023 SOURCE-SELECTION POLICY'

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
VALUES (
    'VETERANS_AFFAIRS',
    'TOTAL_VA_EXPENDITURES',
    'ANNUAL_EXPENDITURES',
    'VA_GDX',
    'VA_GDX',
    ARRAY['USASPENDING_PROCUREMENT']::text[],
    'INCLUDE_AFTER_RECONCILIATION',
    'ANALYSIS-216I-v1: FY2020-FY2023 Washington VA GDX '
    || 'annual expenditure source-selection policy. '
    || 'VA GDX is the preferred annual expenditure and '
    || 'county-allocation source. All 156 county-year '
    || 'observations reconcile exactly: seven legacy '
    || 'expenditure components equal the reported '
    || 'TOTAL_EXPENDITURE control in each county-year. '
    || 'Annual Washington controls are FY2020 '
    || '$5,296,544,030.00; FY2021 $5,323,281,703.03; '
    || 'FY2022 $6,218,866,293.72; FY2023 '
    || '$6,526,168,355.17. Source files are SHA-256 '
    || 'identified in VA GDX load batches 6 through 9. '
    || 'USAspending VA procurement obligations remain '
    || 'provenance and reconciliation evidence and are '
    || 'not automatically additive to GDX expenditures. '
    || 'Functional overlap does not establish '
    || 'dollar-for-dollar containment or same-year '
    || 'expenditure identity. Obligation and expenditure '
    || 'timing differ, and recipient, performance, and '
    || 'beneficiary geographies remain distinct. '
    || 'Exceptions require affirmative evidence of '
    || 'expenditure outside GDX, valid fiscal timing, '
    || 'supported Washington incidence, and no duplication. '
    || 'This policy does not itself authorize final '
    || 'fiscal-balance ledger inclusion. Existing '
    || 'assistance and procurement overlap policies '
    || 'remain unchanged.',
    'ANALYSIS-216I-v1',
    2020,
    2023
);

\echo ''
\echo '3. POST-MIGRATION ASSERTIONS'

DO $gate$
DECLARE
    v_rows bigint;
    v_conflicts bigint;
BEGIN
    SELECT COUNT(*) INTO v_rows
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-216I-v1'
      AND inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND accounting_measure = 'ANNUAL_EXPENDITURES'
      AND preferred_source = 'VA_GDX'
      AND allocation_source = 'VA_GDX'
      AND overlapping_sources =
          ARRAY['USASPENDING_PROCUREMENT']::text[]
      AND ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2023;

    SELECT COUNT(*) INTO v_conflicts
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND methodology_version <> 'ANALYSIS-216I-v1'
      AND (
          valid_from_fiscal_year IS NULL
          OR valid_from_fiscal_year <= 2023
      )
      AND (
          valid_through_fiscal_year IS NULL
          OR valid_through_fiscal_year >= 2020
      );

    IF v_rows <> 1 OR v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'POST-MIGRATION FAILURE: inserted %, conflicts %',
            v_rows, v_conflicts;
    END IF;

    RAISE NOTICE
        'POST-MIGRATION CONTROLS PASS';
END
$gate$;

\echo ''
\echo '4. INSERTED POLICY'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    preferred_source,
    allocation_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-216I-v1';

COMMIT;

\echo ''
\echo 'ETL-216I COMPLETE - COMMIT ISSUED'
