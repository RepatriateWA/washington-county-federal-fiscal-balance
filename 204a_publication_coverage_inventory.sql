BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-204A — EXISTING EVIDENCE AND COVERAGE INVENTORY'
\echo '============================================================'

\echo ''
\echo '1. CMS / MEDICARE / MEDICAID / CHIP OBJECTS'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN ('cms', 'analysis', 'reporting')
  AND (
      table_name ILIKE '%medicare%'
      OR table_name ILIKE '%medicaid%'
      OR table_name ILIKE '%chip%'
      OR table_name ILIKE '%mssp%'
      OR table_name ILIKE '%part_c%'
      OR table_name ILIKE '%part_d%'
  )
ORDER BY table_schema, table_name;

\echo ''
\echo '2. MILITARY / CIVILIAN RETIREMENT OBJECTS'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE (
    table_name ILIKE '%retire%'
    OR table_name ILIKE '%survivor%'
    OR table_name ILIKE '%dfas%'
    OR table_name ILIKE '%pension%'
    OR table_name ILIKE '%annuit%'
)
ORDER BY table_schema, table_name;

\echo ''
\echo '3. VA / WAGE / PROCUREMENT / ASSISTANCE OBJECTS'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'va', 'omb', 'opm', 'bea',
    'procurement', 'assistance',
    'analysis', 'reporting'
)
AND (
    table_name ILIKE '%gdx%'
    OR table_name ILIKE '%wage%'
    OR table_name ILIKE '%procurement%'
    OR table_name ILIKE '%assistance%'
)
ORDER BY table_schema, table_name;

\echo ''
\echo '4. SOURCE POLICY COVERAGE BY FISCAL YEAR'

SELECT
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source,
    p.ledger_treatment,
    y.fiscal_year,
    p.methodology_version
FROM reference.federal_inflow_source_policy p
CROSS JOIN generate_series(2018, 2024) AS y(fiscal_year)
WHERE p.valid_from_fiscal_year <= y.fiscal_year
  AND (
      p.valid_through_fiscal_year IS NULL
      OR p.valid_through_fiscal_year >= y.fiscal_year
  )
ORDER BY
    p.inflow_family,
    p.inflow_subfamily,
    y.fiscal_year;

\echo ''
\echo '5. EXISTING STATEWIDE REPORTING VIEWS'

SELECT
    table_schema,
    table_name
FROM information_schema.views
WHERE table_schema IN ('analysis', 'reporting')
  AND (
      table_name ILIKE '%state%'
      OR table_name ILIKE '%washington%'
      OR table_name ILIKE '%fiscal%'
      OR table_name ILIKE '%balance%'
      OR table_name ILIKE '%ledger%'
  )
ORDER BY table_schema, table_name;

COMMIT;