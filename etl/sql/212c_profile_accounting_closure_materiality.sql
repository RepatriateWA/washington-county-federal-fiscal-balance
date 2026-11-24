
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212C - ACCOUNTING CLOSURE AND MATERIALITY'
\echo 'FY2018-FY2025'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. ANNUAL ASSISTANCE ACCOUNTING CLOSURE
-- ============================================================

\echo ''
\echo '1. ANNUAL ASSISTANCE ACCOUNTING CLOSURE'

WITH program_year AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS net_obligations,
        SUM(
            GREATEST(federal_action_obligation, 0)
        ) AS positive_obligations,
        SUM(
            LEAST(federal_action_obligation, 0)
        ) AS negative_modifications,
        SUM(
            ABS(federal_action_obligation)
        ) AS absolute_activity
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2025
    GROUP BY 1, 2
),
policy_matches AS (
    SELECT
        p.fiscal_year,
        p.program_code,
        p.transaction_count,
        p.net_obligations,
        p.positive_obligations,
        p.negative_modifications,
        p.absolute_activity,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS match_count,
        MIN(m.resolved_accounting_disposition)
            AS disposition
    FROM program_year p
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = p.program_code
     AND p.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, 2018)
         AND COALESCE(m.valid_through_fiscal_year, 2025)
    GROUP BY
        p.fiscal_year,
        p.program_code,
        p.transaction_count,
        p.net_obligations,
        p.positive_obligations,
        p.negative_modifications,
        p.absolute_activity
),
classified AS (
    SELECT
        *,
        CASE
            WHEN program_code IS NULL
                THEN 'MISSING_PROGRAM_CODE'
            WHEN match_count = 0
                THEN 'UNMAPPED'
            WHEN match_count > 1
                THEN 'MULTIPLE_MAPPINGS'
            ELSE COALESCE(
                disposition, 'NULL_DISPOSITION'
            )
        END AS accounting_status
    FROM policy_matches
)
SELECT
    fiscal_year,
    accounting_status,
    COUNT(*) AS program_years,
    SUM(transaction_count) AS transactions,
    ROUND(SUM(net_obligations), 2)
        AS net_obligations,
    ROUND(SUM(positive_obligations), 2)
        AS positive_obligations,
    ROUND(SUM(negative_modifications), 2)
        AS negative_modifications,
    ROUND(SUM(absolute_activity), 2)
        AS absolute_activity,
    ROUND(
        100.0 * SUM(transaction_count)
        / NULLIF(
            SUM(SUM(transaction_count))
                OVER (PARTITION BY fiscal_year), 0
        ), 2
    ) AS transaction_pct,
    ROUND(
        100.0 * SUM(absolute_activity)
        / NULLIF(
            SUM(SUM(absolute_activity))
                OVER (PARTITION BY fiscal_year), 0
        ), 2
    ) AS activity_pct
FROM classified
GROUP BY fiscal_year, accounting_status
ORDER BY fiscal_year, accounting_status;

-- ============================================================
-- 2. HISTORICAL UNRESOLVED MATERIALITY
-- ============================================================

\echo ''
\echo '2. TOP 40 UNMAPPED HISTORICAL PROGRAMS FY2018-FY2024'

WITH program_year AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        MAX(cfda_title) AS program_title,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS net_obligations,
        SUM(
            GREATEST(federal_action_obligation, 0)
        ) AS positive_obligations,
        SUM(
            LEAST(federal_action_obligation, 0)
        ) AS negative_modifications,
        SUM(
            ABS(federal_action_obligation)
        ) AS absolute_activity
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
    GROUP BY 1, 2
),
unmapped AS (
    SELECT p.*
    FROM program_year p
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = p.program_code
          AND p.fiscal_year BETWEEN
              COALESCE(m.valid_from_fiscal_year, 2018)
              AND COALESCE(m.valid_through_fiscal_year, 2025)
    )
)
SELECT
    COALESCE(program_code, '[MISSING]')
        AS program_code,
    MAX(program_title) AS program_title,
    COUNT(*) AS unresolved_years,
    SUM(transaction_count) AS transactions,
    ROUND(SUM(net_obligations), 2)
        AS net_obligations,
    ROUND(SUM(positive_obligations), 2)
        AS positive_obligations,
    ROUND(SUM(negative_modifications), 2)
        AS negative_modifications,
    ROUND(SUM(absolute_activity), 2)
        AS absolute_activity
FROM unmapped
GROUP BY program_code
ORDER BY SUM(absolute_activity) DESC
LIMIT 40;

-- ============================================================
-- 3. FY2025 POLICY EXTENSION CANDIDATES
-- ============================================================

\echo ''
\echo '3. FY2025 UNMAPPED PROGRAMS WITH HISTORICAL POLICY PRECEDENT'

WITH fy2025 AS (
    SELECT
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        MAX(cfda_title) AS program_title,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS net_obligations,
        SUM(ABS(federal_action_obligation))
            AS absolute_activity
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year = 2025
    GROUP BY 1
),
historical AS (
    SELECT
        source_program_code,
        COUNT(*) AS historical_mapping_rows,
        COUNT(DISTINCT resolved_accounting_disposition)
            AS distinct_dispositions,
        STRING_AGG(
            DISTINCT resolved_accounting_disposition,
            ', '
        ) AS historical_dispositions,
        MIN(valid_from_fiscal_year) AS earliest_policy_year,
        MAX(valid_through_fiscal_year) AS latest_policy_year
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND (
          valid_from_fiscal_year IS NULL
          OR valid_from_fiscal_year <= 2024
      )
      AND (
          valid_through_fiscal_year IS NULL
          OR valid_through_fiscal_year >= 2018
      )
    GROUP BY source_program_code
)
SELECT
    f.program_code,
    f.program_title,
    f.transactions,
    ROUND(f.net_obligations, 2) AS net_obligations,
    ROUND(f.absolute_activity, 2) AS absolute_activity,
    h.historical_mapping_rows,
    h.distinct_dispositions,
    h.historical_dispositions,
    h.earliest_policy_year,
    h.latest_policy_year
FROM fy2025 f
JOIN historical h
  ON h.source_program_code = f.program_code
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_program_policy_mapping m
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = f.program_code
      AND 2025 BETWEEN
          COALESCE(m.valid_from_fiscal_year, 2018)
          AND COALESCE(m.valid_through_fiscal_year, 2025)
)
ORDER BY f.absolute_activity DESC
LIMIT 40;

-- ============================================================
-- 4. PROCUREMENT ANNUAL ACTIVITY
-- ============================================================

\echo ''
\echo '4. PROCUREMENT ANNUAL ACTIVITY'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT load_batch_id) AS load_batches,
    ROUND(SUM(federal_action_obligation), 2)
        AS net_obligations,
    ROUND(
        SUM(GREATEST(federal_action_obligation, 0)), 2
    ) AS positive_obligations,
    ROUND(
        SUM(LEAST(federal_action_obligation, 0)), 2
    ) AS negative_modifications,
    ROUND(
        SUM(ABS(federal_action_obligation)), 2
    ) AS absolute_activity
FROM procurement.award_transaction
WHERE fiscal_year BETWEEN 2018 AND 2025
GROUP BY fiscal_year
ORDER BY fiscal_year;

-- ============================================================
-- 5. PROCUREMENT GEOGRAPHIC LINKAGE
-- ============================================================

\echo ''
\echo '5. PROCUREMENT PLACE-OF-PERFORMANCE LINKAGE'

WITH place_summary AS (
    SELECT
        award_transaction_id,
        COUNT(*) AS place_rows,
        BOOL_OR(
            UPPER(BTRIM(state_code)) = 'WA'
        ) AS has_wa_state,
        BOOL_OR(county_id IS NOT NULL)
            AS has_county
    FROM procurement.place_of_performance
    GROUP BY award_transaction_id
),
classified AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.federal_action_obligation,
        CASE
            WHEN p.award_transaction_id IS NULL
                THEN 'NO_PLACE_LINK'
            WHEN p.place_rows > 1
                THEN 'MULTIPLE_PLACE_ROWS'
            WHEN p.has_wa_state AND p.has_county
                THEN 'WA_COUNTY_LINKED'
            WHEN p.has_wa_state
                THEN 'WA_COUNTY_UNRESOLVED'
            ELSE 'OTHER_OR_UNKNOWN_GEOGRAPHY'
        END AS geography_status
    FROM procurement.award_transaction t
    LEFT JOIN place_summary p
      ON p.award_transaction_id = t.award_transaction_id
    WHERE t.fiscal_year BETWEEN 2018 AND 2025
)
SELECT
    fiscal_year,
    geography_status,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation), 2)
        AS net_obligations,
    ROUND(
        SUM(ABS(federal_action_obligation)), 2
    ) AS absolute_activity
FROM classified
GROUP BY fiscal_year, geography_status
ORDER BY fiscal_year, geography_status;

ROLLBACK;

\echo ''
\echo 'ETL-212C COMPLETE - NO DATABASE WRITES'
