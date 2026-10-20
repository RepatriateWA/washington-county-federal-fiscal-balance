
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218H3 - INDEPENDENT POST-MIGRATION VERIFICATION'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. COMMITTED METHODOLOGY NOTE'

SELECT
    methodology_note,
    COUNT(*) AS years
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY methodology_note;

\echo ''
\echo '2. INDEPENDENT ANNUAL ARITHMETIC'

WITH tracked AS (
    SELECT
        report_year,
        COUNT(*) AS component_rows,
        SUM(expenditure_dollars::numeric) AS expenditures
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year
)
SELECT
    p.report_year,
    t.component_rows,
    p.gross_collections_dollars,
    t.expenditures AS independently_summed_expenditures,
    p.tracked_expenditures_dollars,
    t.expenditures - p.tracked_expenditures_dollars
        AS expenditure_difference,
    p.partial_fiscal_balance_dollars,
    p.gross_collections_dollars::numeric
        - t.expenditures
        - p.partial_fiscal_balance_dollars
        AS balance_difference
FROM reporting.v_washington_partial_fiscal_balance p
LEFT JOIN tracked t
    ON t.report_year = p.report_year
WHERE p.report_year BETWEEN 2018 AND 2024
ORDER BY p.report_year;

\echo ''
\echo '3. CMS COMPONENTS VERSUS SOURCE CONTROLS'

WITH expected AS (
    SELECT
        fiscal_year AS report_year,
        'MEDICAID'::text AS program_code,
        federal_expenditure_amount::numeric AS source_dollars
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL

    SELECT
        fiscal_year,
        'CHIP',
        federal_expenditure_amount::numeric
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024
),
tracked AS (
    SELECT
        report_year,
        program_code,
        COUNT(*) AS component_rows,
        SUM(expenditure_dollars::numeric) AS tracked_dollars
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
      AND agency_code = 'CMS'
      AND program_code IN ('MEDICAID','CHIP')
    GROUP BY report_year, program_code
)
SELECT
    e.report_year,
    e.program_code,
    t.component_rows,
    e.source_dollars,
    t.tracked_dollars,
    t.tracked_dollars - e.source_dollars AS difference
FROM expected e
LEFT JOIN tracked t
    ON t.report_year = e.report_year
   AND t.program_code = e.program_code
ORDER BY e.report_year, e.program_code;

\echo ''
\echo '4. COMMITTED NUMERICAL FINGERPRINT'

SELECT
    COUNT(*) AS years,
    SUM(gross_collections_dollars::numeric) AS total_revenue,
    SUM(tracked_expenditures_dollars::numeric)
        AS total_expenditures,
    SUM(partial_fiscal_balance_dollars::numeric)
        AS total_partial_balance,
    MD5(
        STRING_AGG(
            CONCAT_WS(
                '|',
                report_year,
                gross_collections_dollars::numeric,
                tracked_expenditures_dollars::numeric,
                partial_fiscal_balance_dollars::numeric
            ),
            ';' ORDER BY report_year
        )
    ) AS numerical_fingerprint
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2018 AND 2024;

\echo ''
\echo '5. REPORTING DEPENDENCY CHECK'

SELECT DISTINCT
    source_ns.nspname AS source_schema,
    source_rel.relname AS source_relation
FROM pg_depend d
JOIN pg_rewrite rw
    ON rw.oid = d.objid
JOIN pg_class dependent_rel
    ON dependent_rel.oid = rw.ev_class
JOIN pg_namespace dependent_ns
    ON dependent_ns.oid = dependent_rel.relnamespace
JOIN pg_class source_rel
    ON source_rel.oid = d.refobjid
JOIN pg_namespace source_ns
    ON source_ns.oid = source_rel.relnamespace
WHERE dependent_ns.nspname = 'reporting'
  AND dependent_rel.relname =
      'v_washington_partial_fiscal_balance'
  AND source_rel.oid <> dependent_rel.oid
  AND source_rel.relkind IN ('r','p','v','m')
ORDER BY source_schema, source_relation;

\echo ''
\echo '6. FAIL-CLOSED INDEPENDENT CERTIFICATION GATE'

DO $gate$
DECLARE
    v_years integer;
    v_revenue numeric;
    v_expenditures numeric;
    v_balance numeric;
    v_fingerprint text;
    v_bad_notes integer;
    v_bad_arithmetic integer;
    v_bad_cms integer;
    v_bad_dependencies integer;
    v_expected_note text :=
        'Partial balance: IRS gross collections minus ' ||
        'annualized SSA OASDI benefits, Original Medicare ' ||
        'actual payments, CMS Medicaid federal Total Net ' ||
        'Expenditures, and CMS CHIP expenditures. ' ||
        'VA, USAspending, Medicare Advantage, and other ' ||
        'federal expenditures are not yet included.';
BEGIN
    SELECT
        COUNT(*),
        SUM(gross_collections_dollars::numeric),
        SUM(tracked_expenditures_dollars::numeric),
        SUM(partial_fiscal_balance_dollars::numeric),
        MD5(
            STRING_AGG(
                CONCAT_WS(
                    '|',
                    report_year,
                    gross_collections_dollars::numeric,
                    tracked_expenditures_dollars::numeric,
                    partial_fiscal_balance_dollars::numeric
                ),
                ';' ORDER BY report_year
            )
        ),
        COUNT(*) FILTER (
            WHERE methodology_note IS DISTINCT FROM
                  v_expected_note
        )
    INTO
        v_years,
        v_revenue,
        v_expenditures,
        v_balance,
        v_fingerprint,
        v_bad_notes
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year BETWEEN 2018 AND 2024;

    WITH tracked AS (
        SELECT
            report_year,
            COUNT(*) AS n,
            SUM(expenditure_dollars::numeric) AS dollars
        FROM reporting.v_washington_tracked_expenditures
        WHERE report_year BETWEEN 2018 AND 2024
        GROUP BY report_year
    )
    SELECT COUNT(*)
    INTO v_bad_arithmetic
    FROM reporting.v_washington_partial_fiscal_balance p
    LEFT JOIN tracked t
        ON t.report_year = p.report_year
    WHERE p.report_year BETWEEN 2018 AND 2024
      AND (
          COALESCE(t.n,0) <> 6
          OR t.dollars IS DISTINCT FROM
             p.tracked_expenditures_dollars
          OR p.gross_collections_dollars::numeric
             - t.dollars IS DISTINCT FROM
             p.partial_fiscal_balance_dollars
      );

    WITH expected AS (
        SELECT
            fiscal_year AS report_year,
            'MEDICAID'::text AS program_code,
            federal_expenditure_amount::numeric AS dollars
        FROM reporting.v_washington_medicaid_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT
            fiscal_year,
            'CHIP',
            federal_expenditure_amount::numeric
        FROM reporting.v_washington_chip_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024
    ),
    tracked AS (
        SELECT
            report_year,
            program_code,
            COUNT(*) AS n,
            SUM(expenditure_dollars::numeric) AS dollars
        FROM reporting.v_washington_tracked_expenditures
        WHERE report_year BETWEEN 2018 AND 2024
          AND agency_code = 'CMS'
          AND program_code IN ('MEDICAID','CHIP')
        GROUP BY report_year,program_code
    ),
    expected_keys AS (
        SELECT y.report_year, p.program_code
        FROM generate_series(2018,2024) y(report_year)
        CROSS JOIN (
            VALUES ('MEDICAID'::text),('CHIP'::text)
        ) p(program_code)
    )
    SELECT COUNT(*)
    INTO v_bad_cms
    FROM expected_keys k
    LEFT JOIN expected e
        ON e.report_year = k.report_year
       AND e.program_code = k.program_code
    LEFT JOIN tracked t
        ON t.report_year = k.report_year
       AND t.program_code = k.program_code
    GROUP BY k.report_year,k.program_code
    HAVING COUNT(e.report_year) <> 1
        OR MAX(COALESCE(t.n,0)) <> 1
        OR MAX(t.dollars) IS DISTINCT FROM
           MAX(e.dollars);

    WITH dependencies AS (
        SELECT DISTINCT source_rel.relname AS name
        FROM pg_depend d
        JOIN pg_rewrite rw ON rw.oid=d.objid
        JOIN pg_class target ON target.oid=rw.ev_class
        JOIN pg_namespace target_ns
            ON target_ns.oid=target.relnamespace
        JOIN pg_class source_rel
            ON source_rel.oid=d.refobjid
        JOIN pg_namespace source_ns
            ON source_ns.oid=source_rel.relnamespace
        WHERE target_ns.nspname='reporting'
          AND target.relname =
              'v_washington_partial_fiscal_balance'
          AND source_ns.nspname='reporting'
          AND source_rel.oid <> target.oid
          AND source_rel.relkind IN ('r','p','v','m')
    )
    SELECT COUNT(*)
    INTO v_bad_dependencies
    FROM dependencies
    WHERE name NOT IN (
        'v_washington_revenue_summary',
        'v_washington_tracked_expenditures'
    );

    IF v_years <> 7
       OR v_revenue IS DISTINCT FROM 877156759000
       OR v_expenditures IS DISTINCT FROM 323024861111
       OR v_balance IS DISTINCT FROM 554131897889
       OR v_fingerprint IS DISTINCT FROM
           '25a17fdc06e68f50d7c319dc8248f26f'
       OR v_bad_notes <> 0
       OR v_bad_arithmetic <> 0
       OR v_bad_cms <> 0
       OR v_bad_dependencies <> 0 THEN

        RAISE EXCEPTION
            'ETL-218H3 BLOCK: years %, notes %, arithmetic %, CMS %, unexpected dependencies %, fingerprint %',
            v_years,
            v_bad_notes,
            v_bad_arithmetic,
            v_bad_cms,
            v_bad_dependencies,
            v_fingerprint;
    END IF;

    RAISE NOTICE
        'ETL-218H3 PASS: committed methodology and numerical controls verified';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-218H3 COMPLETE - READ ONLY'
