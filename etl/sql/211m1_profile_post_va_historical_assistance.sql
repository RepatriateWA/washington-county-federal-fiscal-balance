
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211M1 - POST-VA HISTORICAL ASSISTANCE INVENTORY'
\echo 'FY2018-FY2019 | READ ONLY | NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. COMPLETE ACCOUNTING DISPOSITION BRIDGE
-- ============================================================

\echo ''
\echo '1. ACCOUNTING DISPOSITIONS BY FISCAL YEAR'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
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
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition,
        COALESCE(
            a.accounting_disposition,
            p.resolved_accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS final_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM resolved
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;

-- ============================================================
-- 2. RANK ALL REMAINING UNRESOLVED PROGRAMS
-- ============================================================

\echo ''
\echo '2. TOP 40 REMAINING UNRESOLVED PROGRAMS'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
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
        COALESCE(
            a.accounting_disposition,
            p.resolved_accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS final_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
)
SELECT
    COALESCE(program_code, '[MISSING]') AS program_code,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (WHERE fiscal_year = 2018)
        AS fy2018_transactions,
    COUNT(*) FILTER (WHERE fiscal_year = 2019)
        AS fy2019_transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM resolved
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY COALESCE(program_code, '[MISSING]')
ORDER BY net_obligations DESC, program_code
LIMIT 40;

-- ============================================================
-- 3. HISTORICAL VA UNRESOLVED PROGRAM INVENTORY
-- ============================================================

\echo ''
\echo '3. ALL REMAINING UNRESOLVED VA PROGRAMS'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
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
        COALESCE(
            a.accounting_disposition,
            p.resolved_accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS final_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM resolved
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
  AND program_code LIKE '64.%'
GROUP BY fiscal_year, program_code
ORDER BY fiscal_year, net_obligations DESC, program_code;

-- ============================================================
-- 4. HISTORICAL VA DISPOSITION SUMMARY
-- ============================================================

\echo ''
\echo '4. VA ASSISTANCE DISPOSITIONS BY FISCAL YEAR'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
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
        COALESCE(
            a.accounting_disposition,
            p.resolved_accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS final_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM resolved
WHERE program_code LIKE '64.%'
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;

-- ============================================================
-- 5. ACCOUNTING INTEGRITY CONTROLS
-- ============================================================

\echo ''
\echo '5. ACCOUNTING INTEGRITY CONTROLS'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
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
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition,
        COALESCE(
            a.accounting_disposition,
            p.resolved_accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS final_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
),
source_controls AS (
    SELECT
        COUNT(*) AS source_rows,
        COALESCE(SUM(obligation), 0) AS source_amount
    FROM historical
),
resolved_controls AS (
    SELECT
        COUNT(*) AS resolved_rows,
        COUNT(DISTINCT assistance_transaction_id)
            AS distinct_rows,
        COALESCE(SUM(obligation), 0) AS resolved_amount,
        COUNT(*) FILTER (
            WHERE program_disposition IS NOT NULL
              AND award_disposition IS NOT NULL
        ) AS program_award_overlaps,
        COUNT(*) FILTER (
            WHERE final_disposition NOT IN (
                'EXCLUDE_DUPLICATE',
                'INCLUDE_ADDITIVE',
                'UNCLASSIFIED_REVIEW',
                'WITHHOLD_UNRESOLVED'
            )
        ) AS unknown_dispositions
    FROM resolved
),
target_controls AS (
    SELECT
        COUNT(*) AS target_rows,
        COALESCE(SUM(obligation), 0) AS target_amount,
        COUNT(*) FILTER (
            WHERE final_disposition <> 'EXCLUDE_DUPLICATE'
        ) AS incorrectly_classified
    FROM resolved
    WHERE program_code IN (
        '64.104','64.105','64.110',
        '64.028','64.032','64.117',
        '64.120','64.124'
    )
)
SELECT
    s.source_rows,
    r.resolved_rows,
    r.distinct_rows,
    ROUND(s.source_amount::numeric, 2)
        AS source_amount,
    ROUND(r.resolved_amount::numeric, 2)
        AS resolved_amount,
    r.program_award_overlaps,
    r.unknown_dispositions,
    t.target_rows,
    ROUND(t.target_amount::numeric, 2)
        AS target_amount,
    t.incorrectly_classified,
    CASE
        WHEN s.source_rows = 207343
         AND r.resolved_rows = s.source_rows
         AND r.distinct_rows = s.source_rows
         AND ROUND(r.resolved_amount, 2) =
             ROUND(s.source_amount, 2)
         AND r.unknown_dispositions = 0
         AND t.target_rows = 5337
         AND ROUND(t.target_amount, 2) = 1274305391.00
         AND t.incorrectly_classified = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS integrity_result
FROM source_controls s
CROSS JOIN resolved_controls r
CROSS JOIN target_controls t;

ROLLBACK;

\echo ''
\echo 'ETL-211M1 COMPLETE - NO DATABASE WRITES'
