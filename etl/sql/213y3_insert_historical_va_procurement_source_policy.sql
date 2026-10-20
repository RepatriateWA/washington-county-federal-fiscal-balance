
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-213Y3 v0.1 - HISTORICAL VA PROCUREMENT SOURCE POLICY'
\echo 'ANALYSIS-213-v1 | FY2018-FY2019 | CONTROLLED MIGRATION'
\echo '============================================================'

BEGIN;
SET LOCAL statement_timeout = '180s';

LOCK TABLE reference.federal_inflow_source_policy
    IN SHARE ROW EXCLUSIVE MODE;

\echo ''
\echo '1. Pre-migration assertions'

DO $$
DECLARE
    v_conflicts integer;
    v_version_rows integer;
    v_fy2024_rows integer;
BEGIN
    SELECT COUNT(*)
    INTO v_conflicts
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND (
          valid_from_fiscal_year IS NULL
          OR valid_through_fiscal_year IS NULL
          OR (
              valid_from_fiscal_year <= 2019
              AND valid_through_fiscal_year >= 2018
          )
      );

    SELECT COUNT(*)
    INTO v_version_rows
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-213-v1';

    SELECT COUNT(*)
    INTO v_fy2024_rows
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 2
      AND inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND methodology_version = 'ANALYSIS-149-v1'
      AND valid_from_fiscal_year = 2024
      AND valid_through_fiscal_year = 2024;

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % historical policy conflicts',
            v_conflicts;
    END IF;

    IF v_version_rows <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: ANALYSIS-213-v1 already exists';
    END IF;

    IF v_fy2024_rows <> 1 THEN
        RAISE EXCEPTION
            'BLOCK: FY2024 policy baseline differs';
    END IF;

    RAISE NOTICE
        'PRE-MIGRATION CONTROLS PASS';
END
$$;

\echo ''
\echo '2. Insert historical source-selection policy'

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
    'ANALYSIS-213-v1: FY2018-FY2019 historical VA GDX '
    || 'source-selection policy. VA GDX is the preferred '
    || 'annual expenditure and county-allocation source. '
    || 'Historical GDX expenditures reconcile exactly to '
    || 'the six expenditure components for all 39 Washington '
    || 'counties in each year. USAspending VA-funded '
    || 'procurement comprises 3,892 FY2018 transactions '
    || 'and $457,642,893.26 net obligations, and 2,530 '
    || 'FY2019 transactions and $412,209,832.19 net '
    || 'obligations. Procurement is preserved for provenance '
    || 'and reconciliation but is not an independently '
    || 'additive expenditure stream. Functional overlap '
    || 'does not prove dollar-for-dollar containment. '
    || 'Obligation timing differs from expenditure timing. '
    || 'Recipient, performance, and beneficiary geographies '
    || 'must remain distinct. Exceptions require affirmative '
    || 'evidence of expenditure outside GDX, valid timing, '
    || 'supported geographic incidence, and no duplication. '
    || 'See notes/analysis_213_v1_historical_va_gdx_'
    || 'procurement_source_policy.md and the historical '
    || 'geographic-incidence policy. Existing FY2024 and '
    || 'historical assistance policies remain unchanged.',
    'ANALYSIS-213-v1',
    2018,
    2019
);

\echo ''
\echo '3. Validate inserted policy'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
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
WHERE methodology_version = 'ANALYSIS-213-v1';

\echo ''
\echo '4. Post-migration assertions'

DO $$
DECLARE
    v_new_rows integer;
    v_fy2024_rows integer;
    v_historical_assistance_rows integer;
    v_policy_total integer;
BEGIN
    SELECT COUNT(*)
    INTO v_new_rows
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-213-v1'
      AND inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND accounting_measure = 'ANNUAL_EXPENDITURES'
      AND preferred_source = 'VA_GDX'
      AND allocation_source = 'VA_GDX'
      AND overlapping_sources =
          ARRAY['USASPENDING_PROCUREMENT']::text[]
      AND ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_fy2024_rows
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 2
      AND methodology_version = 'ANALYSIS-149-v1'
      AND valid_from_fiscal_year = 2024
      AND valid_through_fiscal_year = 2024;

    SELECT COUNT(*)
    INTO v_historical_assistance_rows
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version IN (
        'ANALYSIS-209U-v1',
        'ANALYSIS-211L-v1',
        'ANALYSIS-211M-v1',
        'ANALYSIS-211N-v1'
    )
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_policy_total
    FROM reference.federal_inflow_source_policy;

    IF v_new_rows <> 1
       OR v_fy2024_rows <> 1
       OR v_historical_assistance_rows <> 4
       OR v_policy_total <> 55 THEN
        RAISE EXCEPTION
            'POST-MIGRATION FAILURE: new=%, FY2024=%, assistance=%, total=%',
            v_new_rows,
            v_fy2024_rows,
            v_historical_assistance_rows,
            v_policy_total;
    END IF;

    RAISE NOTICE
        'POST-MIGRATION CONTROLS PASS: new=%, FY2024=%, assistance=%, total=%',
        v_new_rows,
        v_fy2024_rows,
        v_historical_assistance_rows,
        v_policy_total;
END
$$;

COMMIT;

\echo ''
\echo 'ETL-213Y3 v0.1 COMPLETE - COMMIT ISSUED'
