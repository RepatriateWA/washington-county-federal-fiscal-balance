\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE (table_schema, table_name) IN (
    ('reference', 'federal_inflow_program_policy_mapping'),
    ('reference', 'federal_inflow_award_classification')
)
ORDER BY table_schema, table_name, ordinal_position;

SELECT
    'PROGRAM_POLICY' AS policy_type,
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE source_system = 'USASPENDING_ASSISTANCE'
    ) AS assistance_rows,
    COUNT(*) FILTER (
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND 2025 >= COALESCE(valid_from_fiscal_year, -2147483648)
          AND 2025 <= COALESCE(valid_through_fiscal_year, 2147483647)
    ) AS assistance_rows_valid_2025,
    COUNT(*) FILTER (
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND valid_through_fiscal_year = 2024
    ) AS assistance_rows_ending_2024,
    COUNT(*) FILTER (
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND valid_through_fiscal_year IS NULL
    ) AS assistance_rows_open_ended
FROM reference.federal_inflow_program_policy_mapping;

SELECT
    'AWARD_POLICY' AS policy_type,
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE source_system = 'USASPENDING_ASSISTANCE'
    ) AS assistance_rows,
    COUNT(*) FILTER (
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND 2025 >= COALESCE(valid_from_fiscal_year, -2147483648)
          AND 2025 <= COALESCE(valid_through_fiscal_year, 2147483647)
    ) AS assistance_rows_valid_2025,
    COUNT(*) FILTER (
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND valid_through_fiscal_year = 2024
    ) AS assistance_rows_ending_2024,
    COUNT(*) FILTER (
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND valid_through_fiscal_year IS NULL
    ) AS assistance_rows_open_ended
FROM reference.federal_inflow_award_classification;

ROLLBACK;
