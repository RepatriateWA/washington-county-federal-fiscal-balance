
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215C - SEVEN-YEAR ASSISTANCE POLICY RECONCILIATION'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- A single query pipeline applies fiscal-year-valid policies.
-- No temp tables, persistent objects, or source modifications.

\echo ''
\echo '1. ACCOUNTING DISPOSITION BY FISCAL YEAR'

WITH source_rows AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        COALESCE(
            NULLIF(TRIM(award_id_fain), ''),
            NULLIF(TRIM(award_id_uri), '')
        ) AS award_identifier,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE
        (load_batch_id = 20
         AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21
         AND action_date_fiscal_year = 2019)
        OR
        (reference_state_abbreviation = 'WA'
         AND action_date_fiscal_year BETWEEN 2020 AND 2024)
),
award_policies AS (
    SELECT
        s.assistance_transaction_id,
        COUNT(a.federal_inflow_award_classification_id)
            AS match_count,
        MIN(a.accounting_disposition) AS disposition
    FROM source_rows s
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = s.program_code
     AND a.source_award_identifier = s.award_identifier
     AND (
         a.valid_from_fiscal_year IS NULL
         OR a.valid_from_fiscal_year <= s.fiscal_year
     )
     AND (
         a.valid_through_fiscal_year IS NULL
         OR a.valid_through_fiscal_year >= s.fiscal_year
     )
    GROUP BY s.assistance_transaction_id
),
program_policies AS (
    SELECT
        s.assistance_transaction_id,
        COUNT(p.federal_inflow_program_policy_mapping_id)
            AS match_count,
        MIN(p.resolved_accounting_disposition)
            AS disposition
    FROM source_rows s
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = s.program_code
     AND (
         p.valid_from_fiscal_year IS NULL
         OR p.valid_from_fiscal_year <= s.fiscal_year
     )
     AND (
         p.valid_through_fiscal_year IS NULL
         OR p.valid_through_fiscal_year >= s.fiscal_year
     )
    GROUP BY s.assistance_transaction_id
),
resolved AS (
    SELECT
        s.*,
        a.match_count AS award_matches,
        p.match_count AS program_matches,
        CASE
            WHEN a.match_count > 1
              OR p.match_count > 1
                THEN 'POLICY_COLLISION'
            WHEN a.match_count = 1
                THEN a.disposition
            WHEN p.match_count = 1
                THEN p.disposition
            ELSE 'UNMAPPED'
        END AS accounting_disposition,
        CASE
            WHEN a.match_count > 1
              OR p.match_count > 1
                THEN 'COLLISION'
            WHEN a.match_count = 1
                THEN 'AWARD'
            WHEN p.match_count = 1
                THEN 'PROGRAM'
            ELSE 'NONE'
        END AS resolution_layer
    FROM source_rows s
    JOIN award_policies a USING (assistance_transaction_id)
    JOIN program_policies p USING (assistance_transaction_id)
)
SELECT
    fiscal_year,
    accounting_disposition,
    resolution_layer,
    COUNT(*) AS transaction_count,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE award_matches > 1
           OR program_matches > 1
    ) AS collision_transactions
FROM resolved
GROUP BY fiscal_year, accounting_disposition, resolution_layer
ORDER BY fiscal_year, accounting_disposition, resolution_layer;

\echo ''
\echo '2. POLICY WINDOW COLLISION INVENTORY'
\echo 'Overlapping windows may be valid only if never applicable'
\echo 'to the same program and fiscal year.'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    p.source_program_code,
    COUNT(*) AS applicable_program_mappings,
    STRING_AGG(
        p.federal_inflow_program_policy_mapping_id::text,
        ', ' ORDER BY
        p.federal_inflow_program_policy_mapping_id
    ) AS mapping_ids
FROM years y
JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND (
     p.valid_from_fiscal_year IS NULL
     OR p.valid_from_fiscal_year <= y.fiscal_year
 )
 AND (
     p.valid_through_fiscal_year IS NULL
     OR p.valid_through_fiscal_year >= y.fiscal_year
 )
GROUP BY y.fiscal_year, p.source_program_code
HAVING COUNT(*) > 1
ORDER BY y.fiscal_year, p.source_program_code;

\echo ''
\echo '3. HISTORICAL SIX-PROGRAM SOURCE CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE (
    (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR
    (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND TRIM(cfda_number) IN (
    '10.555','84.010','84.027',
    '84.063','93.558','93.600'
)
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '4. SEVEN-YEAR SOURCE UNIVERSE CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transaction_ids,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE
    (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR
    (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    OR
    (reference_state_abbreviation = 'WA'
     AND action_date_fiscal_year BETWEEN 2020 AND 2024)
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-215C COMPLETE - READ ONLY'
