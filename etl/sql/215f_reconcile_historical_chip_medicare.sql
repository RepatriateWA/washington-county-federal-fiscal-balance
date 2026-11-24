
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215F - HISTORICAL CHIP / MEDICARE RECONCILIATION'
\echo 'FY2018-FY2019 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. HISTORICAL SOURCE TRANSACTIONS AND AWARD IDENTIFIERS'

WITH source_rows AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        cfda_number AS program_code,
        assistance_transaction_id,
        federal_action_obligation AS obligation,
        NULLIF(BTRIM(award_id_fain), '') AS fain,
        NULLIF(BTRIM(award_id_uri), '') AS uri,
        COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger
    WHERE
        (action_date_fiscal_year = 2018 AND load_batch_id = 20
         OR action_date_fiscal_year = 2019 AND load_batch_id = 21)
        AND BTRIM(cfda_number) IN ('93.767', '93.770')
),
unmapped AS (
    SELECT s.*
    FROM source_rows s
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = BTRIM(s.program_code)
          AND a.source_award_identifier = s.award_identifier
          AND s.fiscal_year BETWEEN
              a.valid_from_fiscal_year
              AND a.valid_through_fiscal_year
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = BTRIM(s.program_code)
          AND s.fiscal_year BETWEEN
              p.valid_from_fiscal_year
              AND p.valid_through_fiscal_year
    )
)
SELECT
    fiscal_year,
    program_code,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id) AS distinct_ids,
    COUNT(*) FILTER (WHERE fain IS NOT NULL) AS with_fain,
    COUNT(*) FILTER (WHERE uri IS NOT NULL) AS with_uri,
    COUNT(*) FILTER (WHERE award_identifier IS NULL)
        AS missing_award_identifier,
    COUNT(*) FILTER (WHERE obligation < 0)
        AS negative_transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2) AS absolute_activity
FROM unmapped
GROUP BY fiscal_year, program_code
ORDER BY program_code, fiscal_year;

\echo ''
\echo '2. HISTORICAL AWARD-LEVEL PROVENANCE'

SELECT
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), ''),
        '[MISSING]'
    ) AS award_identifier,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(federal_action_obligation))::numeric, 2)
        AS absolute_activity
FROM analysis.v_certified_assistance_ledger
WHERE
    (
        (action_date_fiscal_year = 2018 AND load_batch_id = 20)
        OR
        (action_date_fiscal_year = 2019 AND load_batch_id = 21)
    )
    AND BTRIM(cfda_number) IN ('93.767', '93.770')
GROUP BY
    action_date_fiscal_year,
    BTRIM(cfda_number),
    COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), ''),
        '[MISSING]'
    )
ORDER BY
    program_code,
    fiscal_year,
    absolute_activity DESC;

\echo ''
\echo '3. EXISTING CHIP EXPENDITURE CONTROLS'

SELECT
    fiscal_year,
    ROUND(SUM(federal_expenditure_amount)::numeric, 2)
        AS chip_federal_expenditures,
    COUNT(*) AS source_records,
    STRING_AGG(DISTINCT amount_method, '; ') AS amount_methods,
    STRING_AGG(
        DISTINCT is_additive_to_fiscal_balance::text, '; '
    ) AS additive_flags
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year IN (2018, 2019)
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '4. MEDICARE CORE CONTROLS - CALENDAR YEAR'
\echo 'These are NOT federal-fiscal-year expenditure equivalents.'

SELECT
    calendar_year,
    state_id,
    ROUND(original_medicare_actual_ffs_dollars::numeric, 2)
        AS original_medicare_ffs,
    ROUND(partc_reconstructed_dollars::numeric, 2)
        AS part_c_reconstructed,
    ROUND(partd_reconstructed_dollars::numeric, 2)
        AS part_d_reconstructed,
    partd_coverage_status,
    combined_period_status,
    timing_basis_status,
    ledger_status
FROM cms.medicare_core_state_year
WHERE calendar_year IN (2018, 2019)
ORDER BY calendar_year, state_id;

\echo ''
\echo '5. EXISTING PROGRAM MAPPINGS FOR BOTH PROGRAMS'

SELECT
    source_program_code,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    federal_inflow_source_policy_id
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN ('93.767', '93.770')
ORDER BY source_program_code, valid_from_fiscal_year;

\echo ''
\echo '6. EXISTING AWARD CLASSIFICATIONS FOR BOTH PROGRAMS'

SELECT
    source_program_code,
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN ('93.767', '93.770')
ORDER BY
    source_program_code,
    valid_from_fiscal_year,
    source_award_identifier
LIMIT 100;

\echo ''
\echo '7. RELEVANT EXISTING SOURCE POLICIES'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE
    inflow_family ILIKE '%MEDICARE%'
    OR inflow_family ILIKE '%CHIP%'
    OR inflow_subfamily ILIKE '%MEDICARE%'
    OR inflow_subfamily ILIKE '%CHIP%'
ORDER BY inflow_family, inflow_subfamily, methodology_version;

\echo ''
\echo '8. EXPECTED HISTORICAL UNMAPPED CONTROL'

WITH source_rows AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        BTRIM(cfda_number) AS program_code,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger
    WHERE
        (
            (action_date_fiscal_year = 2018 AND load_batch_id = 20)
            OR
            (action_date_fiscal_year = 2019 AND load_batch_id = 21)
        )
        AND BTRIM(cfda_number) IN ('93.767', '93.770')
),
unmapped AS (
    SELECT s.*
    FROM source_rows s
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND s.fiscal_year BETWEEN
              a.valid_from_fiscal_year
              AND a.valid_through_fiscal_year
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND s.fiscal_year BETWEEN
              p.valid_from_fiscal_year
              AND p.valid_through_fiscal_year
    )
),
totals AS (
    SELECT
        program_code,
        COUNT(*) AS transactions,
        ROUND(SUM(obligation)::numeric, 2) AS net_obligations
    FROM unmapped
    GROUP BY program_code
)
SELECT
    program_code,
    transactions,
    net_obligations,
    CASE
        WHEN program_code = '93.767'
         AND net_obligations = 476425502.00
            THEN 'PASS'
        WHEN program_code = '93.770'
         AND net_obligations = 315496326.00
            THEN 'PASS'
        ELSE 'FAIL'
    END AS control_status
FROM totals
ORDER BY program_code;

ROLLBACK;

\echo ''
\echo 'ETL-215F COMPLETE - READ ONLY'
