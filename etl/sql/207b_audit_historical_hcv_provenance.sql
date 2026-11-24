\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-207B - HISTORICAL HCV PROVENANCE AUDIT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

-- ============================================================
-- 1. AWARD AND RECIPIENT COVERAGE
-- ============================================================

\echo '=== 1. HISTORICAL AWARD AND RECIPIENT COVERAGE ==='

WITH hcv AS (
    SELECT *
    FROM analysis.v_certified_assistance_ledger
    WHERE TRIM(cfda_number) = '14.871'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      )
)
SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT NULLIF(BTRIM(assistance_award_unique_key), ''))
        AS distinct_award_keys,
    COUNT(DISTINCT NULLIF(BTRIM(award_id_fain), ''))
        AS distinct_fains,
    COUNT(DISTINCT recipient_id) AS distinct_recipients,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(assistance_award_unique_key), '') IS NULL
    ) AS missing_award_keys,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(award_id_fain), '') IS NULL
    ) AS missing_fains,
    COUNT(*) FILTER (
        WHERE recipient_id IS NULL
    ) AS missing_recipients,
    SUM(federal_action_obligation) AS net_obligations
FROM hcv
GROUP BY 1
ORDER BY 1;


-- ============================================================
-- 2. GEOGRAPHIC PROVENANCE
-- ============================================================

\echo '=== 2. HISTORICAL HCV GEOGRAPHY ==='

SELECT
    action_date_fiscal_year AS fiscal_year,
    COALESCE(NULLIF(BTRIM(performance_state_code), ''), '<MISSING>')
        AS performance_state,
    COALESCE(NULLIF(BTRIM(reference_state_abbreviation), ''), '<MISSING>')
        AS reference_state,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE TRIM(cfda_number) = '14.871'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY 1, 2, 3
ORDER BY 1, net_obligations DESC;


-- ============================================================
-- 3. COVID AND EXTRAORDINARY PROVENANCE
-- ============================================================

\echo '=== 3. COVID AND EXTRAORDINARY PROVENANCE ==='

SELECT
    action_date_fiscal_year AS fiscal_year,
    COALESCE(is_covid, FALSE) AS is_covid,
    COALESCE(is_iija, FALSE) AS is_iija,
    COALESCE(is_extraordinary, FALSE) AS is_extraordinary,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE TRIM(cfda_number) = '14.871'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;


-- ============================================================
-- 4. EXACT AWARD-KEY COLLISIONS
-- ============================================================

\echo '=== 4. AWARD-KEY COLLISIONS WITH OTHER HUD PROGRAMS ==='

WITH historical AS (
    SELECT
        TRIM(cfda_number) AS program_code,
        NULLIF(BTRIM(assistance_award_unique_key), '') AS award_key
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
      AND TRIM(cfda_number) LIKE '14.%'
),
hcv AS (
    SELECT DISTINCT award_key
    FROM historical
    WHERE program_code = '14.871'
      AND award_key IS NOT NULL
)
SELECT
    o.program_code AS other_program,
    COUNT(DISTINCT o.award_key) AS shared_award_keys
FROM historical o
JOIN hcv h
  ON h.award_key = o.award_key
WHERE o.program_code <> '14.871'
GROUP BY o.program_code
ORDER BY shared_award_keys DESC, other_program;


-- ============================================================
-- 5. FAIN COLLISIONS
-- ============================================================

\echo '=== 5. FAIN COLLISIONS WITH OTHER HUD PROGRAMS ==='

WITH historical AS (
    SELECT
        TRIM(cfda_number) AS program_code,
        NULLIF(BTRIM(award_id_fain), '') AS fain_key
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
      AND TRIM(cfda_number) LIKE '14.%'
),
hcv AS (
    SELECT DISTINCT fain_key
    FROM historical
    WHERE program_code = '14.871'
      AND fain_key IS NOT NULL
)
SELECT
    o.program_code AS other_program,
    COUNT(DISTINCT o.fain_key) AS shared_fains
FROM historical o
JOIN hcv h
  ON h.fain_key = o.fain_key
WHERE o.program_code <> '14.871'
GROUP BY o.program_code
ORDER BY shared_fains DESC, other_program;


-- ============================================================
-- 6. FUNDING AGENCY
-- ============================================================

\echo '=== 6. FUNDING AGENCY PROFILE ==='

SELECT
    action_date_fiscal_year AS fiscal_year,
    funding_agency_code,
    funding_agency_name,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE TRIM(cfda_number) = '14.871'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY 1, 2, 3
ORDER BY 1, net_obligations DESC;


-- ============================================================
-- 7. TRANSACTION KEY UNIQUENESS
-- ============================================================

\echo '=== 7. TRANSACTION KEY UNIQUENESS ==='

SELECT
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_unique_key)
        AS distinct_transaction_keys,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transaction_ids,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(assistance_transaction_unique_key), '')
              IS NULL
    ) AS missing_transaction_keys
FROM analysis.v_certified_assistance_ledger
WHERE TRIM(cfda_number) = '14.871'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  );

COMMIT;

\echo 'ETL-207B READ-ONLY AUDIT COMPLETE'