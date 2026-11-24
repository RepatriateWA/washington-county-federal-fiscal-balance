\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-226C4 - ADDITIVE ASSISTANCE PROGRAM INVENTORY'
\echo 'FY2018-FY2024 - READ ONLY'

BEGIN TRANSACTION READ ONLY;

WITH source_rows AS MATERIALIZED (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        BTRIM(t.cfda_number) AS program_code,
        t.cfda_title AS program_title,
        t.federal_action_obligation AS obligation,
        NULLIF(BTRIM(t.award_id_fain), '') AS fain,
        NULLIF(BTRIM(t.award_id_uri), '') AS uri
    FROM analysis.v_certified_assistance_ledger t
    WHERE
        (t.load_batch_id = 20
         AND t.action_date_fiscal_year = 2018)
        OR
        (t.load_batch_id = 21
         AND t.action_date_fiscal_year = 2019)
        OR
        (t.action_date_fiscal_year BETWEEN 2020 AND 2024
         AND t.reference_state_abbreviation = 'WA')
),
resolved AS MATERIALIZED (
    SELECT
        s.*,
        a.match_count AS award_matches,
        p.match_count AS program_matches,
        CASE
            WHEN a.match_count > 1 OR p.match_count > 1
                THEN 'POLICY_COLLISION'
            WHEN a.match_count = 1
                THEN COALESCE(a.disposition, 'UNCLASSIFIED_REVIEW')
            WHEN p.match_count = 1
                THEN COALESCE(p.disposition, 'UNCLASSIFIED_REVIEW')
            ELSE 'UNCLASSIFIED_REVIEW'
        END AS final_disposition
    FROM source_rows s
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS match_count,
            MIN(c.accounting_disposition) AS disposition
        FROM reference.federal_inflow_award_classification c
        WHERE c.source_system = 'USASPENDING_ASSISTANCE'
          AND BTRIM(c.source_program_code) = s.program_code
          AND (
              c.source_award_identifier = s.fain
              OR c.source_award_identifier = s.uri
          )
          AND (
              c.valid_from_fiscal_year IS NULL
              OR s.fiscal_year >= c.valid_from_fiscal_year
          )
          AND (
              c.valid_through_fiscal_year IS NULL
              OR s.fiscal_year <= c.valid_through_fiscal_year
          )
    ) a ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS match_count,
            MIN(m.resolved_accounting_disposition)
                AS disposition
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND BTRIM(m.source_program_code) = s.program_code
          AND (
              m.valid_from_fiscal_year IS NULL
              OR s.fiscal_year >= m.valid_from_fiscal_year
          )
          AND (
              m.valid_through_fiscal_year IS NULL
              OR s.fiscal_year <= m.valid_through_fiscal_year
          )
    ) p ON TRUE
)
SELECT
    fiscal_year,
    program_code,
    MAX(program_title) AS program_title,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2) AS absolute_activity
FROM resolved
WHERE final_disposition = 'INCLUDE_ADDITIVE'
GROUP BY fiscal_year, program_code
ORDER BY fiscal_year, ABS(SUM(obligation)) DESC;

ROLLBACK;

\echo 'ETL-226C4 COMPLETE - NO DATABASE WRITES'
