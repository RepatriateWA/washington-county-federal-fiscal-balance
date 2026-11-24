
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '=========================================================='
\echo 'ETL-213W v0.1 - HISTORICAL VA GDX CONTROL AND POLICY AUDIT'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '=========================================================='

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Historical GDX load provenance'

SELECT
    gdx_load_batch_id,
    fiscal_year,
    source_file,
    source_sha256,
    schema_regime,
    methodology_regime,
    methodology_break,
    source_county_rows,
    loaded_expenditure_rows,
    rejected_row_count,
    load_status
FROM va.gdx_load_batch
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year, gdx_load_batch_id;

\echo ''
\echo '2. GDX annual control totals'

SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT county_id) AS distinct_counties,
    ROUND(SUM(va_gdx_expenditure_amount), 2)
        AS statewide_gdx_expenditure
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year IN (2018, 2019)
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '3. Historical GDX expenditure categories'

SELECT
    e.fiscal_year,
    e.schema_regime,
    e.expenditure_class,
    e.source_category_name,
    c.category_code,
    c.category_name,
    c.aggregation_role,
    COUNT(*) AS observations,
    COUNT(DISTINCT e.county_id) AS counties,
    ROUND(SUM(e.expenditure_amount), 2)
        AS total_expenditure
FROM va.gdx_county_expenditure e
LEFT JOIN va.gdx_expenditure_category c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
GROUP BY
    e.fiscal_year,
    e.schema_regime,
    e.expenditure_class,
    e.source_category_name,
    c.category_code,
    c.category_name,
    c.aggregation_role
ORDER BY
    e.fiscal_year,
    c.aggregation_role,
    ABS(SUM(e.expenditure_amount)) DESC;

\echo ''
\echo '4. VA-related source policies'

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
    valid_through_fiscal_year,
    source_selection_basis
FROM reference.federal_inflow_source_policy
WHERE
    CONCAT_WS(
        ' ',
        inflow_family,
        inflow_subfamily,
        preferred_source,
        allocation_source,
        overlapping_sources::text,
        source_selection_basis
    ) ~* 'VA_GDX|VETERANS|VA PROCUREMENT|VA_SPENDING'
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year,
    methodology_version;

\echo ''
\echo '5. VA-related program policy mappings'

SELECT
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source,
    p.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE
    CONCAT_WS(
        ' ',
        p.inflow_family,
        p.inflow_subfamily,
        p.preferred_source,
        m.source_program_code
    ) ~* 'VA_GDX|VETERANS|VA PROCUREMENT'
    OR (
        m.source_program_code LIKE '64.%'
        AND m.source_system ILIKE '%USASPENDING%'
    )
ORDER BY
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.methodology_version;

\echo ''
\echo '6. Existing award-level VA-related classifications'

SELECT
    source_system,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS classifications
FROM reference.federal_inflow_award_classification
WHERE
    source_program_code LIKE '64.%'
    OR inflow_family ILIKE '%VETERAN%'
    OR inflow_subfamily ILIKE '%VETERAN%'
GROUP BY
    source_system,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
ORDER BY
    source_system,
    methodology_version,
    accounting_disposition;

ROLLBACK;

\echo ''
\echo 'ETL-213W v0.1 COMPLETE - NO DATABASE WRITES'
