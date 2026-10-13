
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-201Q STAGE C.3A - CORRECTED FIELD PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '900s';

\echo ''
\echo 'SECTION 1 - DATE FORMAT EXAMPLES'

WITH eligible AS MATERIALIZED (
    SELECT r.raw_record
    FROM assistance.raw_award_transaction r
    JOIN assistance.award a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
),
date_values AS (
    SELECT
        v.field_name,
        BTRIM(v.field_value) AS field_value
    FROM eligible e
    CROSS JOIN LATERAL (
        VALUES
            ('action_date', e.raw_record ->> 'action_date'),
            ('initial_report_date',
                e.raw_record ->> 'initial_report_date'),
            ('last_modified_date',
                e.raw_record ->> 'last_modified_date')
    ) v(field_name, field_value)
),
distinct_formats AS (
    SELECT
        field_name,
        field_value,
        COUNT(*) AS occurrence_count,
        ROW_NUMBER() OVER (
            PARTITION BY field_name
            ORDER BY COUNT(*) DESC, field_value
        ) AS example_rank
    FROM date_values
    GROUP BY field_name, field_value
)
SELECT
    field_name,
    field_value AS example_value,
    occurrence_count
FROM distinct_formats
WHERE example_rank <= 5
ORDER BY field_name, example_rank;

\echo ''
\echo 'SECTION 2 - MONETARY FIELD FORMAT PROFILE'

WITH eligible AS MATERIALIZED (
    SELECT r.raw_record
    FROM assistance.raw_award_transaction r
    JOIN assistance.award a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
),
amount_fields AS (
    SELECT
        v.field_name,
        NULLIF(BTRIM(v.field_value), '') AS field_value
    FROM eligible e
    CROSS JOIN LATERAL (
        VALUES
            ('federal_action_obligation',
                e.raw_record ->> 'federal_action_obligation'),
            ('total_obligated_amount',
                e.raw_record ->> 'total_obligated_amount'),
            ('total_outlayed_amount_for_overall_award',
                e.raw_record ->>
                'total_outlayed_amount_for_overall_award'),
            ('indirect_cost_federal_share_amount',
                e.raw_record ->>
                'indirect_cost_federal_share_amount'),
            ('non_federal_funding_amount',
                e.raw_record ->> 'non_federal_funding_amount'),
            ('total_non_federal_funding_amount',
                e.raw_record ->>
                'total_non_federal_funding_amount'),
            ('face_value_of_loan',
                e.raw_record ->> 'face_value_of_loan'),
            ('original_loan_subsidy_cost',
                e.raw_record ->> 'original_loan_subsidy_cost'),
            ('total_face_value_of_loan',
                e.raw_record ->> 'total_face_value_of_loan'),
            ('total_loan_subsidy_cost',
                e.raw_record ->> 'total_loan_subsidy_cost'),
            ('generated_pragmatic_obligations',
                e.raw_record ->>
                'generated_pragmatic_obligations'),
            ('covid_overall_award_obligation',
                e.raw_record ->>
                'obligated_amount_from_COVID-19_supplementals_for_overall_award'),
            ('covid_overall_award_outlay',
                e.raw_record ->>
                'outlayed_amount_from_COVID-19_supplementals_for_overall_award'),
            ('iija_overall_award_obligation',
                e.raw_record ->>
                'obligated_amount_from_IIJA_supplemental_for_overall_award'),
            ('iija_overall_award_outlay',
                e.raw_record ->>
                'outlayed_amount_from_IIJA_supplemental_for_overall_award')
    ) v(field_name, field_value)
)
SELECT
    field_name,
    COUNT(*) AS observations,
    COUNT(*) FILTER (
        WHERE field_value IS NULL
    ) AS missing_values,
    COUNT(*) FILTER (
        WHERE field_value ~
            '^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$'
    ) AS decimal_shapes,
    COUNT(*) FILTER (
        WHERE field_value IS NOT NULL
          AND field_value !~
            '^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$'
    ) AS other_numeric_shapes
FROM amount_fields
GROUP BY field_name
ORDER BY field_name;

\echo ''
\echo 'SECTION 3 - FISCAL YEAR FORMAT PROFILE'

WITH eligible AS MATERIALIZED (
    SELECT
        r.raw_record ->> 'action_date_fiscal_year'
            AS fiscal_year_value
    FROM assistance.raw_award_transaction r
    JOIN assistance.award a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
)
SELECT
    COUNT(*) AS observations,
    COUNT(*) FILTER (
        WHERE fiscal_year_value ~ '^[0-9]{4}$'
    ) AS four_digit_years,
    COUNT(*) FILTER (
        WHERE fiscal_year_value IS NULL
           OR fiscal_year_value !~ '^[0-9]{4}$'
    ) AS invalid_year_shapes
FROM eligible;

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE C.3A COMPLETE - READ ONLY'
