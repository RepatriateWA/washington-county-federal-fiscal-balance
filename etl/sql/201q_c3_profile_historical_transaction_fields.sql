
\set ON_ERROR_STOP on
\pset pager off

\echo '=============================================================='
\echo 'ETL-201Q STAGE C.3 - HISTORICAL FIELD PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '900s';

\echo ''
\echo 'SECTION 1 - ELIGIBLE TRANSACTION IDENTITY'

WITH eligible AS MATERIALIZED (
    SELECT r.*
    FROM assistance.raw_award_transaction r
    JOIN assistance.award a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
)
SELECT
    load_batch_id,
    COUNT(*) AS eligible_observations,
    COUNT(DISTINCT assistance_transaction_unique_key)
        AS distinct_transaction_keys,
    COUNT(*) FILTER (
        WHERE BTRIM(assistance_transaction_unique_key) = ''
    ) AS blank_transaction_keys,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(raw_record ->> 'action_date'), '')
              IS NULL
    ) AS missing_action_dates,
    COUNT(*) FILTER (
        WHERE NULLIF(
            BTRIM(raw_record ->> 'federal_action_obligation'),
            ''
        ) IS NULL
    ) AS missing_action_obligations
FROM eligible
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo 'SECTION 2 - DATE FIELD FORMAT PROFILE'

WITH eligible AS MATERIALIZED (
    SELECT r.raw_record
    FROM assistance.raw_award_transaction r
    JOIN assistance.award a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
),
date_fields AS (
    SELECT
        v.field_name,
        NULLIF(BTRIM(v.field_value), '') AS field_value
    FROM eligible e
    CROSS JOIN LATERAL (
        VALUES
            ('action_date', e.raw_record ->> 'action_date'),
            ('initial_report_date',
                e.raw_record ->> 'initial_report_date'),
            ('last_modified_date',
                e.raw_record ->> 'last_modified_date')
    ) v(field_name, field_value)
)
SELECT
    field_name,
    COUNT(*) AS observations,
    COUNT(*) FILTER (
        WHERE field_value IS NULL
    ) AS missing_values,
    COUNT(*) FILTER (
        WHERE field_value ~ '^\d{4}-\d{2}-\d{2}$'
    ) AS iso_date_shapes,
    COUNT(*) FILTER (
        WHERE field_value IS NOT NULL
          AND field_value !~ '^\d{4}-\d{2}-\d{2}$'
    ) AS other_date_shapes
FROM date_fields
GROUP BY field_name
ORDER BY field_name;

\echo ''
\echo 'SECTION 3 - MONETARY FIELD FORMAT PROFILE'

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
                e.raw_record ->
                > 'indirect_cost_federal_share_amount'),
            ('non_federal_funding_amount',
                e.raw_record ->> 'non_federal_funding_amount'),
            ('total_non_federal_funding_amount',
                e.raw_record ->
                > 'total_non_federal_funding_amount'),
            ('face_value_of_loan',
                e.raw_record ->> 'face_value_of_loan'),
            ('original_loan_subsidy_cost',
                e.raw_record ->> 'original_loan_subsidy_cost'),
            ('total_face_value_of_loan',
                e.raw_record ->> 'total_face_value_of_loan'),
            ('total_loan_subsidy_cost',
                e.raw_record ->> 'total_loan_subsidy_cost'),
            ('generated_pragmatic_obligations',
                e.raw_record ->
                > 'generated_pragmatic_obligations')
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

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE C.3 COMPLETE - READ ONLY'
