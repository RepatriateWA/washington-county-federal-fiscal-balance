
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218H1 - REPORTING METHODOLOGY PREFLIGHT'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. TARGET VIEW DEFINITION'

SELECT pg_get_viewdef(
    'reporting.v_washington_partial_fiscal_balance'::regclass,
    true
) AS view_definition;

\echo ''
\echo '2. TARGET VIEW COLUMN CONTRACT'

SELECT
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable
FROM information_schema.columns
WHERE table_schema='reporting'
  AND table_name='v_washington_partial_fiscal_balance'
ORDER BY ordinal_position;

\echo ''
\echo '3. BASELINE SEVEN-YEAR BALANCES'

SELECT
    report_year,
    gross_collections_dollars,
    tracked_expenditures_dollars,
    partial_fiscal_balance_dollars,
    methodology_note
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year;

\echo ''
\echo '4. CMS MEDICAID AND CHIP REPRESENTATION'

SELECT
    report_year,
    program_code,
    COUNT(*) AS component_rows,
    SUM(expenditure_dollars::numeric) AS dollars
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
  AND agency_code='CMS'
  AND program_code IN ('MEDICAID','CHIP')
GROUP BY report_year,program_code
ORDER BY report_year,program_code;

\echo ''
\echo '5. INDEPENDENT NUMERICAL FINGERPRINT'

WITH annual AS (
    SELECT
        report_year,
        gross_collections_dollars::numeric AS revenue,
        tracked_expenditures_dollars::numeric AS expenditures,
        partial_fiscal_balance_dollars::numeric AS balance
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year BETWEEN 2018 AND 2024
)
SELECT
    COUNT(*) AS years,
    SUM(revenue) AS total_revenue,
    SUM(expenditures) AS total_expenditures,
    SUM(balance) AS total_partial_balance,
    MD5(
        STRING_AGG(
            CONCAT_WS(
                '|',
                report_year,
                revenue,
                expenditures,
                balance
            ),
            ';'
            ORDER BY report_year
        )
    ) AS numerical_fingerprint
FROM annual;

\echo ''
\echo '6. PREFLIGHT SAFETY GATE'

DO $gate$
DECLARE
    v_years integer;
    v_bad_arithmetic integer;
    v_bad_components integer;
    v_bad_notes integer;
BEGIN
    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE gross_collections_dollars::numeric
                - tracked_expenditures_dollars::numeric
                IS DISTINCT FROM partial_fiscal_balance_dollars::numeric
        ),
        COUNT(*) FILTER (
            WHERE methodology_note IS NULL
               OR methodology_note NOT ILIKE '%CHIP%'
        )
    INTO v_years,v_bad_arithmetic,v_bad_notes
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year BETWEEN 2018 AND 2024;

    WITH expected AS (
        SELECT
            y.report_year,
            p.program_code
        FROM generate_series(2018,2024) y(report_year)
        CROSS JOIN (
            VALUES ('MEDICAID'::text),('CHIP'::text)
        ) p(program_code)
    ),
    actual AS (
        SELECT
            report_year,
            program_code,
            COUNT(*) AS n
        FROM reporting.v_washington_tracked_expenditures
        WHERE agency_code='CMS'
          AND program_code IN ('MEDICAID','CHIP')
          AND report_year BETWEEN 2018 AND 2024
        GROUP BY report_year,program_code
    )
    SELECT COUNT(*)
    INTO v_bad_components
    FROM expected e
    LEFT JOIN actual a
      ON a.report_year=e.report_year
     AND a.program_code=e.program_code
    WHERE COALESCE(a.n,0)<>1;

    IF v_years<>7
       OR v_bad_arithmetic<>0
       OR v_bad_components<>0
       OR v_bad_notes<>0 THEN
        RAISE EXCEPTION
            'ETL-218H1 BLOCK: years %, arithmetic %, CMS components %, notes %',
            v_years,
            v_bad_arithmetic,
            v_bad_components,
            v_bad_notes;
    END IF;

    RAISE NOTICE
        'ETL-218H1 PASS: 7 years, 14 CMS components, arithmetic intact';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-218H1 COMPLETE - READ ONLY'
