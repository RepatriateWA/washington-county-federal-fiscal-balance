
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211L2 - HISTORICAL VA LEDGER CERTIFICATION'
\echo 'FY2018-FY2019 | READ ONLY | NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. INSTALLED POLICY RECORDS
-- ============================================================

\echo ''
\echo '1. INSTALLED POLICY RECORDS'

SELECT 'program_classification' AS record_type,
       COUNT(*) AS record_count
FROM reference.federal_inflow_program_classification
WHERE methodology_version = 'ANALYSIS-211L-v1'

UNION ALL

SELECT 'source_policy', COUNT(*)
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-211L-v1'

UNION ALL

SELECT 'program_policy_mapping', COUNT(*)
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-211L-v1';

-- ============================================================
-- 2. TARGET TRANSACTION EFFECTIVE DISPOSITIONS
-- ============================================================

\echo ''
\echo '2. TARGET PROGRAM-YEAR EFFECTIVE DISPOSITIONS'

WITH targets(program_code, family) AS (
    VALUES
    ('64.104','COMPENSATION_PENSION'),
    ('64.105','COMPENSATION_PENSION'),
    ('64.110','COMPENSATION_PENSION'),
    ('64.028','EDUCATION_VRE'),
    ('64.032','EDUCATION_VRE'),
    ('64.117','EDUCATION_VRE'),
    ('64.120','EDUCATION_VRE'),
    ('64.124','EDUCATION_VRE')
),
historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        t.family,
        c.federal_action_obligation,
        c.award_id_fain,
        c.award_id_uri
    FROM analysis.v_certified_assistance_ledger c
    JOIN targets t
      ON t.program_code = BTRIM(c.cfda_number)
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
),
resolved AS (
    SELECT
        h.*,
        m.resolved_accounting_disposition AS program_disposition,
        m.methodology_version,
        COALESCE(
            (
                SELECT MAX(a.accounting_disposition)
                FROM reference.federal_inflow_award_classification a
                WHERE a.source_system = 'USASPENDING_ASSISTANCE'
                  AND a.source_program_code = h.program_code
                  AND a.source_award_identifier IN (
                      h.award_id_fain, h.award_id_uri
                  )
                  AND h.fiscal_year BETWEEN
                      COALESCE(a.valid_from_fiscal_year, -9999)
                      AND COALESCE(a.valid_through_fiscal_year, 9999)
            ),
            m.resolved_accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS effective_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, -9999)
         AND COALESCE(m.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    family,
    program_code,
    effective_disposition,
    methodology_version,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM resolved
GROUP BY
    fiscal_year, family, program_code,
    effective_disposition, methodology_version
ORDER BY fiscal_year, family, program_code,
         effective_disposition;

-- ============================================================
-- 3. EXCLUDED ANCHOR AND UNRESOLVED MEMORIAL PROGRAMS
-- ============================================================

\echo ''
\echo '3. PRESERVED ANCHOR AND MEMORIAL DISPOSITIONS'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger c
    WHERE BTRIM(c.cfda_number) IN (
        '64.109', '64.101', '64.203', '64.206'
    )
    AND (
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
    )
),
resolved AS (
    SELECT
        h.*,
        COALESCE(
            m.resolved_accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS program_disposition,
        m.methodology_version
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, -9999)
         AND COALESCE(m.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    program_code,
    program_disposition,
    methodology_version,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM resolved
GROUP BY fiscal_year, program_code,
         program_disposition, methodology_version
ORDER BY fiscal_year, program_code;

-- ============================================================
-- 4. INDEPENDENT CERTIFICATION GATE
-- ============================================================

\echo ''
\echo '4. INDEPENDENT CERTIFICATION GATE'

WITH targets(program_code) AS (
    VALUES
    ('64.104'),('64.105'),('64.110'),
    ('64.028'),('64.032'),('64.117'),
    ('64.120'),('64.124')
),
historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation,
        c.award_id_fain,
        c.award_id_uri
    FROM analysis.v_certified_assistance_ledger c
    JOIN targets t
      ON t.program_code = BTRIM(c.cfda_number)
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
),
resolution AS (
    SELECT
        h.assistance_transaction_id,
        h.fiscal_year,
        h.program_code,
        h.federal_action_obligation,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS mapping_count,
        COUNT(*) FILTER (
            WHERE m.resolved_accounting_disposition =
                      'EXCLUDE_DUPLICATE'
              AND m.methodology_version = 'ANALYSIS-211L-v1'
              AND s.preferred_source = 'VA_GDX'
        ) AS correct_mapping_count,
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_award_classification a
            WHERE a.source_system = 'USASPENDING_ASSISTANCE'
              AND a.source_program_code = h.program_code
              AND a.source_award_identifier IN (
                  h.award_id_fain, h.award_id_uri
              )
              AND h.fiscal_year BETWEEN
                  COALESCE(a.valid_from_fiscal_year, -9999)
                  AND COALESCE(a.valid_through_fiscal_year, 9999)
        ) AS award_override_count
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, -9999)
         AND COALESCE(m.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    GROUP BY
        h.assistance_transaction_id,
        h.fiscal_year,
        h.program_code,
        h.federal_action_obligation,
        h.award_id_fain,
        h.award_id_uri
),
summary AS (
    SELECT
        COUNT(*) AS transactions,
        COALESCE(SUM(federal_action_obligation), 0)
            AS obligations,
        COUNT(DISTINCT (fiscal_year, program_code))
            AS program_years,
        COUNT(*) FILTER (
            WHERE mapping_count <> 1
               OR correct_mapping_count <> 1
               OR award_override_count <> 0
        ) AS invalid_transactions
    FROM resolution
),
installed AS (
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_classification
         WHERE methodology_version = 'ANALYSIS-211L-v1')
            AS classification_count,
        (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = 'ANALYSIS-211L-v1')
            AS policy_count,
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = 'ANALYSIS-211L-v1')
            AS mapping_count
)
SELECT
    s.transactions,
    ROUND(s.obligations::numeric, 2) AS obligations,
    s.program_years,
    s.invalid_transactions,
    i.classification_count,
    i.policy_count,
    i.mapping_count,
    CASE
        WHEN s.transactions = 5337
         AND ROUND(s.obligations, 2) = 1274305391.00
         AND s.program_years = 16
         AND s.invalid_transactions = 0
         AND i.classification_count = 8
         AND i.policy_count = 1
         AND i.mapping_count = 8
        THEN 'PASS'
        ELSE 'FAIL'
    END AS certification_result
FROM summary s
CROSS JOIN installed i;

ROLLBACK;

\echo ''
\echo 'ETL-211L2 COMPLETE - NO DATABASE WRITES'
