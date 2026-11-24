
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-223C - HISTORICAL UNCLASSIFIED POLICY CROSSWALK'
\echo 'FY2018-FY2019 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

WITH target_programs(program_code, activity_rank) AS (
    VALUES
      ('93.527',1), ('10.557',2), ('10.561',3),
      ('93.563',4), ('10.924',5), ('93.659',6),
      ('93.959',7), ('10.069',8), ('14.267',9),
      ('93.210',10), ('93.242',11), ('93.859',12),
      ('10.112',13), ('15.022',14), ('84.126',15),
      ('16.575',16), ('14.850',17), ('84.041',18),
      ('93.568',19), ('93.441',20)
),
policy_rows AS (
    SELECT
        t.activity_rank,
        t.program_code,
        m.methodology_version,
        m.resolved_accounting_disposition,
        m.valid_from_fiscal_year,
        m.valid_through_fiscal_year,
        m.federal_inflow_source_policy_id,
        s.preferred_source,
        s.accounting_measure,
        s.ledger_treatment,
        s.overlapping_sources
    FROM target_programs t
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = t.program_code
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
)
SELECT
    activity_rank,
    program_code,
    methodology_version,
    resolved_accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    preferred_source,
    accounting_measure,
    ledger_treatment,
    overlapping_sources
FROM policy_rows
ORDER BY activity_rank, valid_from_fiscal_year,
         methodology_version;

\echo ''
\echo 'CROSSWALK COVERAGE SUMMARY'

WITH target_programs(program_code) AS (
    VALUES
      ('93.527'), ('10.557'), ('10.561'),
      ('93.563'), ('10.924'), ('93.659'),
      ('93.959'), ('10.069'), ('14.267'),
      ('93.210'), ('93.242'), ('93.859'),
      ('10.112'), ('15.022'), ('84.126'),
      ('16.575'), ('14.850'), ('84.041'),
      ('93.568'), ('93.441')
)
SELECT
    COUNT(*) AS target_programs,
    COUNT(*) FILTER (
        WHERE EXISTS (
            SELECT 1
            FROM reference.federal_inflow_program_policy_mapping m
            WHERE m.source_system = 'USASPENDING_ASSISTANCE'
              AND m.source_program_code = t.program_code
        )
    ) AS with_any_policy,
    COUNT(*) FILTER (
        WHERE NOT EXISTS (
            SELECT 1
            FROM reference.federal_inflow_program_policy_mapping m
            WHERE m.source_system = 'USASPENDING_ASSISTANCE'
              AND m.source_program_code = t.program_code
        )
    ) AS without_policy
FROM target_programs t;

ROLLBACK;

\echo 'ETL-223C COMPLETE - NO DATABASE WRITES'
