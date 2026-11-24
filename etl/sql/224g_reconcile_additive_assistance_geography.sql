
\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-224G - HISTORICAL ADDITIVE ASSISTANCE GEOGRAPHY'
\echo 'FY2018-FY2019 / READ ONLY'

BEGIN TRANSACTION READ ONLY;

WITH source_rows AS (
    SELECT
        t.assistance_transaction_id,
        t.action_date_fiscal_year AS fiscal_year,
        BTRIM(t.cfda_number) AS program_code,
        COALESCE(
            NULLIF(BTRIM(t.award_id_fain), ''),
            NULLIF(BTRIM(t.award_id_uri), '')
        ) AS award_identifier,
        t.federal_action_obligation AS obligation,
        t.geographic_attribution_class,
        t.is_washington_attributed
    FROM analysis.v_assistance_geographic_attribution t
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
        CASE
            WHEN a.match_count > 1
              OR p.match_count > 1
                THEN 'POLICY_COLLISION'
            WHEN a.match_count = 1
                THEN a.disposition
            WHEN p.match_count = 1
                THEN p.disposition
            ELSE 'UNCLASSIFIED_REVIEW'
        END AS final_disposition
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
            MAX(m.resolved_accounting_disposition)
                AS disposition
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
    geographic_attribution_class,
    is_washington_attributed,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM resolved
WHERE final_disposition = 'INCLUDE_ADDITIVE'
GROUP BY
    fiscal_year,
    final_disposition,
    geographic_attribution_class,
    is_washington_attributed
ORDER BY
    fiscal_year,
    geographic_attribution_class;

ROLLBACK;

\echo 'ETL-224G COMPLETE - NO DATABASE WRITES'
