\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-226C3 - SEVEN-YEAR ASSISTANCE POLICY RECOVERY'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

WITH source_rows AS MATERIALIZED (
    SELECT
        t.assistance_transaction_id,
        t.action_date_fiscal_year AS fiscal_year,
        BTRIM(t.cfda_number) AS program_code,
        t.federal_action_obligation AS obligation,
        NULLIF(BTRIM(t.award_id_fain), '') AS fain,
        NULLIF(BTRIM(t.award_id_uri), '') AS uri
    FROM analysis.v_certified_assistance_ledger t
    WHERE
        (
            t.load_batch_id = 20
            AND t.action_date_fiscal_year = 2018
        )
        OR (
            t.load_batch_id = 21
            AND t.action_date_fiscal_year = 2019
        )
        OR (
            t.action_date_fiscal_year BETWEEN 2020 AND 2024
            AND t.reference_state_abbreviation = 'WA'
        )
),
resolved AS MATERIALIZED (
    SELECT
        s.*,
        a.match_count AS award_matches,
        p.match_count AS program_matches,
        a.disposition AS award_disposition,
        p.disposition AS program_disposition,
        CASE
            WHEN a.match_count > 1 OR p.match_count > 1
                THEN 'POLICY_COLLISION'
            WHEN a.match_count = 1
                THEN COALESCE(
                    a.disposition, 'UNCLASSIFIED_REVIEW'
                )
            WHEN p.match_count = 1
                THEN COALESCE(
                    p.disposition, 'UNCLASSIFIED_REVIEW'
                )
            ELSE 'UNCLASSIFIED_REVIEW'
        END AS final_disposition,
        CASE
            WHEN a.match_count = 1 AND p.match_count <= 1
                THEN 'AWARD'
            WHEN a.match_count = 0 AND p.match_count = 1
                THEN 'PROGRAM'
            ELSE 'NONE_OR_COLLISION'
        END AS resolution_layer
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
    final_disposition,
    resolution_layer,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(COALESCE(SUM(obligation), 0)::numeric, 2)
        AS net_obligations,
    ROUND(
        COALESCE(
            SUM(GREATEST(obligation, 0)), 0
        )::numeric, 2
    ) AS positive_obligations,
    ROUND(
        COALESCE(
            SUM(LEAST(obligation, 0)), 0
        )::numeric, 2
    ) AS negative_modifications,
    COUNT(*) FILTER (
        WHERE award_matches = 1
          AND program_matches = 1
          AND award_disposition
              IS DISTINCT FROM program_disposition
    ) AS award_program_disagreements,
    COUNT(*) FILTER (
        WHERE obligation IS NULL
    ) AS null_amount_rows
FROM resolved
GROUP BY
    fiscal_year,
    final_disposition,
    resolution_layer
ORDER BY
    fiscal_year,
    final_disposition,
    resolution_layer;

ROLLBACK;

\echo 'ETL-226C3 COMPLETE - NO DATABASE WRITES'
