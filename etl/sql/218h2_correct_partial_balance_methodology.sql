
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218H2 - CORRECT PARTIAL-BALANCE METHODOLOGY'
\echo 'CONTROLLED VIEW-TEXT CHANGE / NO ACCOUNTING CHANGES'
\echo '============================================================'

BEGIN;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. VERIFY ORIGINAL DEFINITION AND APPLY TEXT CORRECTION'

DO $migration$
DECLARE
    v_definition text;
    v_revised text;
    v_old_medicaid text :=
        'and CMS Medicaid federal Total Net Expenditures. ';
    v_new_medicaid text :=
        'CMS Medicaid federal Total Net Expenditures, and CMS CHIP expenditures. ';
    v_old_exclusions text :=
        'CHIP, VA, USAspending, Medicare Advantage, and other ';
    v_new_exclusions text :=
        'VA, USAspending, Medicare Advantage, and other ';
    v_old_note text :=
        'Partial balance: IRS gross collections minus annualized ' ||
        'SSA OASDI benefits, Original Medicare actual payments, ' ||
        'and CMS Medicaid federal Total Net Expenditures. ' ||
        'CHIP, VA, USAspending, Medicare Advantage, and other ' ||
        'federal expenditures are not yet included.';
    v_years integer;
    v_fingerprint text;
BEGIN
    SELECT pg_get_viewdef(
        'reporting.v_washington_partial_fiscal_balance'::regclass,
        true
    )
    INTO v_definition;

    IF v_definition IS NULL THEN
        RAISE EXCEPTION 'Target view definition unavailable';
    END IF;

    IF (
        length(v_definition)
        - length(replace(v_definition,v_old_medicaid,''))
    ) / length(v_old_medicaid) <> 1
    OR (
        length(v_definition)
        - length(replace(v_definition,v_old_exclusions,''))
    ) / length(v_old_exclusions) <> 1 THEN
        RAISE EXCEPTION
            'Expected methodology fragments not uniquely present';
    END IF;

    SELECT COUNT(*)
    INTO v_years
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year BETWEEN 2018 AND 2024
      AND methodology_note = v_old_note;

    IF v_years <> 7 THEN
        RAISE EXCEPTION
            'Expected old methodology note on 7 years; found %',
            v_years;
    END IF;

    SELECT MD5(
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
    )
    INTO v_fingerprint
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year BETWEEN 2018 AND 2024;

    IF v_fingerprint <>
       '25a17fdc06e68f50d7c319dc8248f26f' THEN
        RAISE EXCEPTION
            'Pre-migration fingerprint mismatch: %',
            v_fingerprint;
    END IF;

    v_revised := replace(
        replace(
            v_definition,
            v_old_medicaid,
            v_new_medicaid
        ),
        v_old_exclusions,
        v_new_exclusions
    );

    EXECUTE
        'CREATE OR REPLACE VIEW ' ||
        'reporting.v_washington_partial_fiscal_balance AS ' ||
        v_revised;

    RAISE NOTICE
        'ETL-218H2: methodology text replaced; accounting expressions preserved';
END
$migration$;

\echo ''
\echo '2. POST-MIGRATION NUMERICAL VERIFICATION'

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
                '|',report_year,revenue,expenditures,balance
            ),
            ';' ORDER BY report_year
        )
    ) AS numerical_fingerprint
FROM annual;

\echo ''
\echo '3. FAIL-CLOSED POST-MIGRATION GATE'

DO $verify$
DECLARE
    v_years integer;
    v_revenue numeric;
    v_expenditures numeric;
    v_balance numeric;
    v_fingerprint text;
    v_bad_notes integer;
BEGIN
    WITH annual AS (
        SELECT
            report_year,
            gross_collections_dollars::numeric AS revenue,
            tracked_expenditures_dollars::numeric AS expenditures,
            partial_fiscal_balance_dollars::numeric AS balance,
            methodology_note
        FROM reporting.v_washington_partial_fiscal_balance
        WHERE report_year BETWEEN 2018 AND 2024
    )
    SELECT
        COUNT(*),
        SUM(revenue),
        SUM(expenditures),
        SUM(balance),
        MD5(
            STRING_AGG(
                CONCAT_WS(
                    '|',report_year,revenue,expenditures,balance
                ),
                ';' ORDER BY report_year
            )
        ),
        COUNT(*) FILTER (
            WHERE methodology_note IS DISTINCT FROM
                'Partial balance: IRS gross collections minus ' ||
                'annualized SSA OASDI benefits, Original Medicare ' ||
                'actual payments, CMS Medicaid federal Total Net ' ||
                'Expenditures, and CMS CHIP expenditures. ' ||
                'VA, USAspending, Medicare Advantage, and other ' ||
                'federal expenditures are not yet included.'
        )
    INTO
        v_years,
        v_revenue,
        v_expenditures,
        v_balance,
        v_fingerprint,
        v_bad_notes
    FROM annual;

    IF v_years <> 7
       OR v_revenue IS DISTINCT FROM 877156759000
       OR v_expenditures IS DISTINCT FROM 323024861111
       OR v_balance IS DISTINCT FROM 554131897889
       OR v_fingerprint IS DISTINCT FROM
           '25a17fdc06e68f50d7c319dc8248f26f'
       OR v_bad_notes <> 0 THEN
        RAISE EXCEPTION
            'ETL-218H2 BLOCK: numerical or methodology verification failed';
    END IF;

    RAISE NOTICE
        'ETL-218H2 PASS: 7 years, exact fingerprint, corrected methodology';
END
$verify$;

COMMIT;

\echo ''
\echo 'ETL-218H2 COMPLETE - COMMITTED'
