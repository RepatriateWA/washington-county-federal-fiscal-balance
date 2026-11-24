
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218G - WASHINGTON EXPENDITURE LEDGER LINEAGE AUDIT'
\echo 'FY2018-FY2024 / READ ONLY / NO LEDGER PROMOTION'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '240s';

\echo ''
\echo '1. REPORTING VIEW DEFINITIONS'

SELECT
    c.relname AS view_name,
    pg_get_viewdef(c.oid, true) AS view_definition
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'reporting'
  AND c.relname IN (
      'v_washington_tracked_expenditures',
      'v_washington_partial_fiscal_balance',
      'v_washington_medicaid_expenditures',
      'v_washington_chip_expenditures'
  )
  AND c.relkind = 'v'
ORDER BY c.relname;

\echo ''
\echo '2. TRACKED EXPENDITURE COMPONENTS BY YEAR'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    expenditure_dollars,
    measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year,agency_code,program_code;

\echo ''
\echo '3. MEDICAID AND CHIP SOURCE CONTROLS'

WITH cms AS (
    SELECT
        fiscal_year,
        'MEDICAID'::text AS program,
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
)
SELECT
    fiscal_year,
    program,
    COUNT(*) AS source_rows,
    SUM(dollars) AS source_dollars
FROM cms
GROUP BY fiscal_year,program
ORDER BY fiscal_year,program;

\echo ''
\echo '4. TRACKED MEDICAID AND CHIP REPRESENTATION'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    expenditure_dollars,
    measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
  AND (
      UPPER(COALESCE(program_code,'')) LIKE '%MEDICAID%'
      OR UPPER(COALESCE(program_code,'')) LIKE '%CHIP%'
      OR UPPER(COALESCE(program_name,'')) LIKE '%MEDICAID%'
      OR UPPER(COALESCE(program_name,'')) LIKE '%CHIP%'
  )
ORDER BY report_year,program_code;

\echo ''
\echo '5. PARTIAL FISCAL BALANCE RECONCILIATION'

WITH tracked AS (
    SELECT
        report_year,
        SUM(expenditure_dollars::numeric) AS reproduced_expenditures,
        COUNT(*) AS component_rows
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year
),
revenue AS (
    SELECT
        fiscal_year AS report_year,
        gross_collections_dollars::numeric AS reproduced_revenue
    FROM reporting.v_washington_revenue_summary
    WHERE fiscal_year BETWEEN 2018 AND 2024
)
SELECT
    y.report_year,
    r.reproduced_revenue,
    t.component_rows,
    t.reproduced_expenditures,
    p.tracked_expenditures_dollars,
    t.reproduced_expenditures
        - p.tracked_expenditures_dollars
        AS expenditure_difference,
    r.reproduced_revenue
        - t.reproduced_expenditures
        AS reproduced_partial_balance,
    p.partial_fiscal_balance_dollars,
    (r.reproduced_revenue-t.reproduced_expenditures)
        - p.partial_fiscal_balance_dollars
        AS balance_difference
FROM generate_series(2018,2024) y(report_year)
LEFT JOIN revenue r USING (report_year)
LEFT JOIN tracked t USING (report_year)
LEFT JOIN reporting.v_washington_partial_fiscal_balance p
  USING (report_year)
ORDER BY y.report_year;

\echo ''
\echo '6. POTENTIAL DUPLICATE COMPONENT KEYS'

SELECT
    report_year,
    agency_code,
    program_code,
    COUNT(*) AS component_count,
    SUM(expenditure_dollars::numeric) AS combined_dollars
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY report_year,agency_code,program_code
HAVING COUNT(*) > 1
ORDER BY report_year,agency_code,program_code;

\echo ''
\echo '7. DIRECT REPORTING DEPENDENCIES'

SELECT
    source_ns.nspname AS source_schema,
    source_rel.relname AS source_relation,
    dependent_rel.relname AS dependent_view
FROM pg_depend d
JOIN pg_rewrite rw
  ON rw.oid=d.objid
JOIN pg_class dependent_rel
  ON dependent_rel.oid=rw.ev_class
JOIN pg_namespace dependent_ns
  ON dependent_ns.oid=dependent_rel.relnamespace
JOIN pg_class source_rel
  ON source_rel.oid=d.refobjid
JOIN pg_namespace source_ns
  ON source_ns.oid=source_rel.relnamespace
WHERE dependent_ns.nspname='reporting'
  AND dependent_rel.relname IN (
      'v_washington_tracked_expenditures',
      'v_washington_partial_fiscal_balance',
      'v_washington_medicaid_expenditures',
      'v_washington_chip_expenditures'
  )
  AND source_rel.oid <> dependent_rel.oid
  AND source_rel.relkind IN ('r','p','v','m')
GROUP BY
    source_ns.nspname,
    source_rel.relname,
    dependent_rel.relname
ORDER BY dependent_view,source_schema,source_relation;

\echo ''
\echo '8. FAIL-CLOSED ARITHMETIC AND UNIQUENESS GATE'

DO $gate$
DECLARE
    v_bad_years bigint;
    v_duplicate_keys bigint;
    v_bad_cms bigint;
BEGIN
    WITH tracked AS (
        SELECT
            report_year,
            COUNT(*) AS n,
            SUM(expenditure_dollars::numeric) AS dollars
        FROM reporting.v_washington_tracked_expenditures
        WHERE report_year BETWEEN 2018 AND 2024
        GROUP BY report_year
    ),
    revenue AS (
        SELECT
            fiscal_year AS report_year,
            COUNT(*) AS n,
            SUM(gross_collections_dollars::numeric) AS dollars
        FROM reporting.v_washington_revenue_summary
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
    ),
    balance AS (
        SELECT
            report_year,
            COUNT(*) AS n,
            SUM(gross_collections_dollars::numeric) AS revenue,
            SUM(tracked_expenditures_dollars::numeric) AS expenditure,
            SUM(partial_fiscal_balance_dollars::numeric) AS net
        FROM reporting.v_washington_partial_fiscal_balance
        WHERE report_year BETWEEN 2018 AND 2024
        GROUP BY report_year
    )
    SELECT COUNT(*) INTO v_bad_years
    FROM generate_series(2018,2024) y(report_year)
    LEFT JOIN tracked t USING (report_year)
    LEFT JOIN revenue r USING (report_year)
    LEFT JOIN balance b USING (report_year)
    WHERE COALESCE(t.n,0)=0
       OR COALESCE(r.n,0)<>1
       OR COALESCE(b.n,0)<>1
       OR r.dollars IS DISTINCT FROM b.revenue
       OR t.dollars IS DISTINCT FROM b.expenditure
       OR (r.dollars-t.dollars) IS DISTINCT FROM b.net;

    SELECT COUNT(*) INTO v_duplicate_keys
    FROM (
        SELECT report_year,agency_code,program_code
        FROM reporting.v_washington_tracked_expenditures
        WHERE report_year BETWEEN 2018 AND 2024
        GROUP BY report_year,agency_code,program_code
        HAVING COUNT(*)<>1
    ) d;

    WITH cms AS (
        SELECT
            fiscal_year,
            'MEDICAID'::text AS program,
            COUNT(*) AS n,
            SUM(federal_expenditure_amount::numeric) AS dollars
        FROM reporting.v_washington_medicaid_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year

        UNION ALL

        SELECT
            fiscal_year,
            'CHIP',
            COUNT(*),
            SUM(federal_expenditure_amount::numeric)
        FROM reporting.v_washington_chip_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
    ),
    expected AS (
        SELECT
            y.fiscal_year,
            p.program
        FROM generate_series(2018,2024) y(fiscal_year)
        CROSS JOIN (
            VALUES ('MEDICAID'::text),('CHIP'::text)
        ) p(program)
    )
    SELECT COUNT(*) INTO v_bad_cms
    FROM expected e
    LEFT JOIN cms c
      ON c.fiscal_year=e.fiscal_year
     AND c.program=e.program
    WHERE COALESCE(c.n,0)<>1
       OR c.dollars IS NULL
       OR c.dollars<=0;

    IF v_bad_years<>0
       OR v_duplicate_keys<>0
       OR v_bad_cms<>0 THEN
        RAISE EXCEPTION
            'ETL-218G BLOCK: balance failures %, duplicate keys %, CMS control failures %',
            v_bad_years,v_duplicate_keys,v_bad_cms;
    END IF;

    RAISE NOTICE
        'ETL-218G ARITHMETIC PASS: 7 YEARS, UNIQUE COMPONENT KEYS, 14 CMS CONTROLS';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-218G COMPLETE - READ ONLY'
