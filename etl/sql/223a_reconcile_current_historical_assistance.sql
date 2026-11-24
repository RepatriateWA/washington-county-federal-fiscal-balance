
\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-223A - HISTORICAL ASSISTANCE CURRENT-STATE AUDIT'
\echo 'FY2018-FY2019 / READ ONLY / NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

WITH source_rows AS (
    SELECT
        t.assistance_transaction_id,
        t.action_date_fiscal_year AS fiscal_year,
        BTRIM(t.cfda_number) AS program_code,
        t.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(t.award_id_fain), ''),
            NULLIF(BTRIM(t.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger t
    WHERE
        (t.load_batch_id = 20
         AND t.action_date_fiscal_year = 2018)
        OR
        (t.load_batch_id = 21
         AND t.action_date_fiscal_year = 2019)
),
resolved AS (
    SELECT
        s.*,
        a.match_count AS award_matches,
        p.match_count AS program_matches,
        a.disposition AS award_disposition,
        p.disposition AS program_disposition,
        CASE
            WHEN a.match_count > 1
              OR p.match_count > 1
                THEN 'POLICY_COLLISION'
            WHEN a.match_count = 1
                THEN a.disposition
            WHEN p.match_count = 1
                THEN p.disposition
            ELSE 'UNCLASSIFIED_REVIEW'
        END AS final_disposition,
        CASE
            WHEN a.match_count = 1 THEN 'AWARD'
            WHEN p.match_count = 1 THEN 'PROGRAM'
            ELSE 'NONE'
        END AS resolution_layer
    FROM source_rows s

    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS match_count,
            MAX(c.accounting_disposition) AS disposition
        FROM reference.federal_inflow_award_classification c
        WHERE c.source_system = 'USASPENDING_ASSISTANCE'
          AND c.source_program_code = s.program_code
          AND c.source_award_identifier = s.award_identifier
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
            MAX(m.resolved_accounting_disposition) AS disposition
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = s.program_code
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
    final_disposition,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    COUNT(*) FILTER (
        WHERE resolution_layer = 'AWARD'
    ) AS award_resolved,
    COUNT(*) FILTER (
        WHERE resolution_layer = 'PROGRAM'
    ) AS program_resolved,
    COUNT(*) FILTER (
        WHERE award_matches > 0
          AND program_matches > 0
    ) AS both_layers,
    COUNT(*) FILTER (
        WHERE award_matches = 1
          AND program_matches = 1
          AND award_disposition IS DISTINCT FROM program_disposition
    ) AS differing_layer_dispositions
FROM resolved
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;

COMMIT;

\echo 'ETL-223A COMPLETE - NO DATABASE WRITES'
