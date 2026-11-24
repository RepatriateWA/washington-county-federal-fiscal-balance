
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219B4 - VA GDX FY2024 NULL SEMANTICS PROFILE'
\echo 'READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. NULL OBSERVATIONS BY EXPENDITURE CATEGORY'

SELECT
    e.expenditure_class,
    c.category_code,
    c.aggregation_role,
    COUNT(*) AS observations,
    COUNT(*) FILTER (
        WHERE e.expenditure_amount IS NULL
    ) AS null_observations,
    COUNT(*) FILTER (
        WHERE e.expenditure_amount = 0
    ) AS explicit_zero_observations,
    COUNT(*) FILTER (
        WHERE e.expenditure_amount <> 0
    ) AS nonzero_observations,
    SUM(e.expenditure_amount) AS known_dollars
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year = 2024
GROUP BY
    e.expenditure_class,
    c.category_code,
    c.aggregation_role
ORDER BY e.expenditure_class,c.category_code;

\echo ''
\echo '2. CONTROL COMPLETENESS AND COMPONENT RECONCILIATION'

WITH by_class AS (
    SELECT
        e.county_id,
        e.expenditure_class,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
              AND e.expenditure_amount IS NULL
        ) AS null_components,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
              AND e.expenditure_amount IS NULL
        ) AS null_controls,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_rows,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS known_component_dollars,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_dollars
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year = 2024
    GROUP BY e.county_id,e.expenditure_class
)
SELECT
    expenditure_class,
    COUNT(*) AS counties,
    SUM(null_components) AS null_component_observations,
    SUM(null_controls) AS null_control_observations,
    COUNT(*) FILTER (
        WHERE control_rows <> 1
    ) AS invalid_control_counts,
    COUNT(*) FILTER (
        WHERE known_component_dollars
              IS DISTINCT FROM control_dollars
    ) AS reconciliation_failures,
    SUM(control_dollars) AS statewide_control_dollars
FROM by_class
GROUP BY expenditure_class
ORDER BY expenditure_class;

\echo ''
\echo '3. SOURCE COLUMN METADATA FOR NULL INTERPRETATION'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'va'
  AND table_name IN (
      'gdx_county_expenditure',
      'gdx_load_batch',
      'gdx_expenditure_category'
  )
ORDER BY table_name,ordinal_position;

\echo ''
\echo '4. FY2024 SOURCE BATCH PROVENANCE'

SELECT
    fiscal_year,
    source_file,
    source_sha256,
    schema_regime,
    methodology_regime,
    methodology_break,
    load_status,
    source_county_rows,
    loaded_expenditure_rows,
    rejected_row_count
FROM va.gdx_load_batch
WHERE fiscal_year = 2024
ORDER BY gdx_load_batch_id;

\echo ''
\echo '5. FAIL-CLOSED CONTROL INTEGRITY GATE'

DO $gate$
DECLARE
    v_county_classes bigint;
    v_bad_controls bigint;
    v_bad_reconciliations bigint;
    v_null_controls bigint;
    v_null_components bigint;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION
            'BLOCK: transaction is not read-only';
    END IF;

    WITH by_class AS (
        SELECT
            e.county_id,
            e.expenditure_class,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS control_rows,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
                  AND e.expenditure_amount IS NULL
            ) AS null_controls,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
                  AND e.expenditure_amount IS NULL
            ) AS null_components,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS components,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS controls
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year = 2024
        GROUP BY e.county_id,e.expenditure_class
    )
    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE control_rows <> 1
               OR expenditure_class NOT IN ('DIRECT','INDIRECT')
        ),
        COUNT(*) FILTER (
            WHERE components IS DISTINCT FROM controls
        ),
        COALESCE(SUM(null_controls),0),
        COALESCE(SUM(null_components),0)
    INTO
        v_county_classes,
        v_bad_controls,
        v_bad_reconciliations,
        v_null_controls,
        v_null_components
    FROM by_class;

    IF v_county_classes IS DISTINCT FROM 78
       OR v_bad_controls IS DISTINCT FROM 0
       OR v_bad_reconciliations IS DISTINCT FROM 0
       OR v_null_controls IS DISTINCT FROM 0
    THEN
        RAISE EXCEPTION
            'BLOCK: class rows %, bad controls %, reconciliation failures %, NULL controls %',
            v_county_classes,
            v_bad_controls,
            v_bad_reconciliations,
            v_null_controls;
    END IF;

    RAISE NOTICE
        'ETL-219B4 CONTROL INTEGRITY PASS; NULL components retained as unresolved: %',
        v_null_components;
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219B4 COMPLETE - READ ONLY'
