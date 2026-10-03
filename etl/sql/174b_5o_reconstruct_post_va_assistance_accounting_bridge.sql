/*
================================================================================
ETL-174B-5O
Post-VA Assistance Accounting Bridge
================================================================================

Purpose
-------
Reconstruct the Washington FY2020-FY2024 USAspending assistance accounting
bridge after ETL-179 persisted explicit VA assistance accounting policy.

This is a READ-ONLY analytical script.

Resolution hierarchy
--------------------
1. Award-specific accounting classification
2. Explicit program -> source-policy mapping
3. UNCLASSIFIED_REVIEW

Important
---------
* Award-specific classification overrides program-level mapping.
* No fuzzy family/subfamily inference.
* COVID / IIJA / extraordinary status is orthogonal to accounting disposition.
* No database writes.
* ETL-174B-5M remains the frozen pre-VA baseline.

5M baseline
-----------
Gross assistance             348,524,407,674.34
EXCLUDE_DUPLICATE             211,461,499,583.03
INCLUDE_ADDITIVE                5,716,864,764.39
WITHHOLD_UNRESOLVED               354,113,811.43
UNCLASSIFIED_REVIEW           130,991,929,515.49

ETL-179 VA control
------------------
Programs                                  49
Transactions                         59,160
Obligations                 23,707,643,332.28
COVID                         306,522,432.91

No DB writes are authorized by this script.
================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5O POST-VA ASSISTANCE ACCOUNTING BRIDGE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. BUILD BASE FY2020-FY2024 WASHINGTON ASSISTANCE UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5o_base;

CREATE TEMP TABLE etl174b_5o_base AS
SELECT
    l.assistance_transaction_id,
    l.action_date_fiscal_year,
    l.cfda_number,
    l.cfda_title,
    l.award_id_fain,
    l.recipient_name,
    l.funding_agency_name,
    l.federal_action_obligation,
    l.defc_codes,
    l.funding_families,
    l.is_covid,
    l.is_iija,
    l.is_extraordinary
FROM analysis.v_certified_assistance_ledger l
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024;


-- ================================================================================================
-- 2. GROSS CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. GROSS ASSISTANCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS distinct_program_count,
    ROUND(SUM(federal_action_obligation), 2) AS gross_assistance,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount
FROM etl174b_5o_base;


-- ================================================================================================
-- 3. HARD GROSS CONTROL ASSERTION
-- ================================================================================================

DO $$
DECLARE
    v_transaction_count bigint;
    v_gross numeric;
    v_covid numeric;
    v_iija numeric;
    v_extraordinary numeric;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(
                CASE
                    WHEN is_covid
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ),
        COALESCE(
            SUM(
                CASE
                    WHEN is_iija
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ),
        COALESCE(
            SUM(
                CASE
                    WHEN is_extraordinary
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        )
    INTO
        v_transaction_count,
        v_gross,
        v_covid,
        v_iija,
        v_extraordinary
    FROM etl174b_5o_base;

    IF v_transaction_count <> 942243 THEN
        RAISE EXCEPTION
            '5O GROSS CONTROL FAILED: expected 942243 transactions, found %',
            v_transaction_count;
    END IF;

    IF ABS(v_gross - 348524407674.34::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5O GROSS CONTROL FAILED: expected %, found %',
            348524407674.34,
            v_gross;
    END IF;

    IF ABS(v_covid - 46859546247.83::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5O COVID CONTROL FAILED: expected %, found %',
            46859546247.83,
            v_covid;
    END IF;

    IF ABS(v_iija - 8129817959.24::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5O IIJA CONTROL FAILED: expected %, found %',
            8129817959.24,
            v_iija;
    END IF;

    IF ABS(v_extraordinary - 56543893060.40::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5O EXTRAORDINARY CONTROL FAILED: expected %, found %',
            56543893060.40,
            v_extraordinary;
    END IF;

    RAISE NOTICE
        '5O GROSS CONTROL PASS: transactions=% gross=% COVID=% IIJA=% extraordinary=%',
        v_transaction_count,
        v_gross,
        v_covid,
        v_iija,
        v_extraordinary;
END
$$;


-- ================================================================================================
-- 4. RESOLVE AWARD-SPECIFIC CLASSIFICATION
--
-- If multiple historical methodology rows exist for an award, prefer the most
-- recent classification row deterministically.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5o_award_resolution;

CREATE TEMP TABLE etl174b_5o_award_resolution AS
SELECT
    b.*,
    ac.accounting_disposition AS award_disposition,
    ac.methodology_version AS award_methodology_version
FROM etl174b_5o_base b
LEFT JOIN LATERAL (
    SELECT
        a.accounting_disposition,
        a.methodology_version
    FROM reference.federal_inflow_award_classification a
    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code = b.cfda_number
      AND a.source_award_identifier = b.award_id_fain
      AND (
            a.valid_from_fiscal_year IS NULL
            OR b.action_date_fiscal_year >= a.valid_from_fiscal_year
          )
      AND (
            a.valid_through_fiscal_year IS NULL
            OR b.action_date_fiscal_year <= a.valid_through_fiscal_year
          )
    ORDER BY
        a.updated_at DESC NULLS LAST,
        a.created_at DESC NULLS LAST,
        a.federal_inflow_award_classification_id DESC
    LIMIT 1
) ac ON TRUE;


-- ================================================================================================
-- 5. RESOLVE EXPLICIT PROGRAM-POLICY MAPPING
--
-- Mapping is explicit. No fuzzy matching is permitted.
--
-- If multiple historical methodology rows cover the same program/year, prefer
-- the most recently persisted mapping deterministically. This allows ETL-179
-- to supersede older analytical mappings for VA without deleting provenance.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5o_program_resolution;

CREATE TEMP TABLE etl174b_5o_program_resolution AS
SELECT
    a.*,
    pm.resolved_accounting_disposition AS program_disposition,
    pm.methodology_version AS program_methodology_version,
    pm.federal_inflow_source_policy_id
FROM etl174b_5o_award_resolution a
LEFT JOIN LATERAL (
    SELECT
        m.resolved_accounting_disposition,
        m.methodology_version,
        m.federal_inflow_source_policy_id
    FROM reference.federal_inflow_program_policy_mapping m
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = a.cfda_number
      AND (
            m.valid_from_fiscal_year IS NULL
            OR a.action_date_fiscal_year >= m.valid_from_fiscal_year
          )
      AND (
            m.valid_through_fiscal_year IS NULL
            OR a.action_date_fiscal_year <= m.valid_through_fiscal_year
          )
    ORDER BY
        m.updated_at DESC NULLS LAST,
        m.created_at DESC NULLS LAST,
        m.federal_inflow_program_policy_mapping_id DESC
    LIMIT 1
) pm ON TRUE;


-- ================================================================================================
-- 6. FINAL RESOLUTION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5o_resolved;

CREATE TEMP TABLE etl174b_5o_resolved AS
SELECT
    p.*,

    CASE
        WHEN p.award_disposition IS NOT NULL
            THEN 'AWARD'
        WHEN p.program_disposition IS NOT NULL
            THEN 'PROGRAM'
        ELSE 'UNCLASSIFIED'
    END AS resolution_level,

    COALESCE(
        p.award_disposition,
        p.program_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS resolved_accounting_disposition

FROM etl174b_5o_program_resolution p;


-- ================================================================================================
-- 7. ASSERT ONE RESOLVED ROW PER BASE TRANSACTION
-- ================================================================================================

DO $$
DECLARE
    v_base_count bigint;
    v_resolved_count bigint;
    v_distinct_transactions bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_base_count
    FROM etl174b_5o_base;

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id)
    INTO
        v_resolved_count,
        v_distinct_transactions
    FROM etl174b_5o_resolved;

    IF v_resolved_count <> v_base_count THEN
        RAISE EXCEPTION
            '5O ROW CARDINALITY FAILED: base=% resolved=%',
            v_base_count,
            v_resolved_count;
    END IF;

    IF v_distinct_transactions <> v_base_count THEN
        RAISE EXCEPTION
            '5O TRANSACTION UNIQUENESS FAILED: expected %, found % distinct IDs',
            v_base_count,
            v_distinct_transactions;
    END IF;

    RAISE NOTICE
        '5O CARDINALITY PASS: % transactions resolved exactly once',
        v_base_count;
END
$$;


-- ================================================================================================
-- 8. RESOLUTION LEVEL SUMMARY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. RESOLUTION LEVEL SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_level,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl174b_5o_resolved
GROUP BY resolution_level
ORDER BY resolution_level;


-- ================================================================================================
-- 9. FINAL ACCOUNTING DISPOSITION BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. POST-VA ACCOUNTING DISPOSITION BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS distinct_program_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount
FROM etl174b_5o_resolved
GROUP BY resolved_accounting_disposition
ORDER BY resolved_accounting_disposition;


-- ================================================================================================
-- 10. HARD BRIDGE CLOSURE
-- ================================================================================================

DO $$
DECLARE
    v_gross numeric;
    v_resolved numeric;
    v_difference numeric;
BEGIN
    SELECT COALESCE(SUM(federal_action_obligation), 0)
    INTO v_gross
    FROM etl174b_5o_base;

    SELECT COALESCE(SUM(federal_action_obligation), 0)
    INTO v_resolved
    FROM etl174b_5o_resolved;

    v_difference := v_resolved - v_gross;

    IF ABS(v_difference) > 0.01 THEN
        RAISE EXCEPTION
            '5O BRIDGE CLOSURE FAILED: gross=% resolved=% difference=%',
            v_gross,
            v_resolved,
            v_difference;
    END IF;

    RAISE NOTICE
        '5O BRIDGE CLOSURE PASS: gross=% resolved=% difference=%',
        v_gross,
        v_resolved,
        v_difference;
END
$$;


-- ================================================================================================
-- 11. ANNUAL ACCOUNTING BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. ANNUAL ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl174b_5o_resolved
GROUP BY
    action_date_fiscal_year,
    resolved_accounting_disposition
ORDER BY
    action_date_fiscal_year,
    resolved_accounting_disposition;


-- ================================================================================================
-- 12. VA POST-179 BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. VA ASSISTANCE POST-ETL-179 BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl174b_5o_resolved
WHERE cfda_number LIKE '64.%'
GROUP BY resolved_accounting_disposition
ORDER BY resolved_accounting_disposition;


-- ================================================================================================
-- 13. HARD VA CONTROL
-- ================================================================================================

DO $$
DECLARE
    v_program_count integer;
    v_transaction_count bigint;
    v_total numeric;
    v_covid numeric;
    v_unclassified bigint;
BEGIN
    SELECT
        COUNT(DISTINCT cfda_number),
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(
                CASE
                    WHEN is_covid
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
        )
    INTO
        v_program_count,
        v_transaction_count,
        v_total,
        v_covid,
        v_unclassified
    FROM etl174b_5o_resolved
    WHERE cfda_number LIKE '64.%';

    IF v_program_count <> 49 THEN
        RAISE EXCEPTION
            '5O VA CONTROL FAILED: expected 49 programs, found %',
            v_program_count;
    END IF;

    IF v_transaction_count <> 59160 THEN
        RAISE EXCEPTION
            '5O VA CONTROL FAILED: expected 59160 transactions, found %',
            v_transaction_count;
    END IF;

    IF ABS(v_total - 23707643332.28::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5O VA CONTROL FAILED: expected %, found %',
            23707643332.28,
            v_total;
    END IF;

    IF ABS(v_covid - 306522432.91::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5O VA COVID CONTROL FAILED: expected %, found %',
            306522432.91,
            v_covid;
    END IF;

    IF v_unclassified <> 0 THEN
        RAISE EXCEPTION
            '5O VA RESOLUTION FAILED: % VA transactions remain unclassified',
            v_unclassified;
    END IF;

    RAISE NOTICE
        '5O VA CONTROL PASS: 49 programs; 59160 transactions; total=%; COVID=%; unclassified=0',
        v_total,
        v_covid;
END
$$;


-- ================================================================================================
-- 14. 64.015 CHECK
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. VA 64.015 STATE NURSING HOME CARE CHECK'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl174b_5o_resolved
WHERE cfda_number = '64.015'
GROUP BY
    action_date_fiscal_year,
    resolved_accounting_disposition
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 15. 5M -> 5O CHANGE BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. ETL-174B-5M -> 5O CHANGE BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

WITH baseline AS (
    SELECT *
    FROM (
        VALUES
            ('EXCLUDE_DUPLICATE'::text,   211461499583.03::numeric),
            ('INCLUDE_ADDITIVE'::text,      5716864764.39::numeric),
            ('WITHHOLD_UNRESOLVED'::text,    354113811.43::numeric),
            ('UNCLASSIFIED_REVIEW'::text, 130991929515.49::numeric)
    ) v(disposition, amount)
),
current_bridge AS (
    SELECT
        resolved_accounting_disposition AS disposition,
        SUM(federal_action_obligation)::numeric AS amount
    FROM etl174b_5o_resolved
    GROUP BY resolved_accounting_disposition
),
all_dispositions AS (
    SELECT disposition FROM baseline
    UNION
    SELECT disposition FROM current_bridge
)
SELECT
    d.disposition,
    ROUND(COALESCE(b.amount, 0), 2) AS baseline_5m_amount,
    ROUND(COALESCE(c.amount, 0), 2) AS post_va_5o_amount,
    ROUND(
        COALESCE(c.amount, 0) - COALESCE(b.amount, 0),
        2
    ) AS change_from_5m
FROM all_dispositions d
LEFT JOIN baseline b
  ON b.disposition = d.disposition
LEFT JOIN current_bridge c
  ON c.disposition = d.disposition
ORDER BY d.disposition;


-- ================================================================================================
-- 16. UNCLASSIFIED RESIDUAL BY FUNDING AGENCY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. REMAINING UNCLASSIFIED REVIEW BY FUNDING AGENCY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    funding_agency_name,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl174b_5o_resolved
WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY funding_agency_name
ORDER BY SUM(federal_action_obligation) DESC NULLS LAST;


-- ================================================================================================
-- 17. TOP 50 REMAINING UNCLASSIFIED PROGRAMS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TOP 50 REMAINING UNCLASSIFIED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    cfda_title,
    funding_agency_name,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount
FROM etl174b_5o_resolved
WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY
    cfda_number,
    cfda_title,
    funding_agency_name
ORDER BY SUM(federal_action_obligation) DESC NULLS LAST
LIMIT 50;


-- ================================================================================================
-- 18. TOP 50 REMAINING UNCLASSIFIED AWARDS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. TOP 50 REMAINING UNCLASSIFIED AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    cfda_title,
    award_id_fain,
    recipient_name,
    funding_agency_name,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl174b_5o_resolved
WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY
    cfda_number,
    cfda_title,
    award_id_fain,
    recipient_name,
    funding_agency_name
ORDER BY SUM(federal_action_obligation) DESC NULLS LAST
LIMIT 50;


-- ================================================================================================
-- 19. FINAL SUMMARY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. FINAL SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH s AS (
    SELECT
        SUM(federal_action_obligation)
            FILTER (
                WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
            ) AS unclassified_amount,

        SUM(federal_action_obligation)
            FILTER (
                WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
            ) AS excluded_amount,

        SUM(federal_action_obligation)
            FILTER (
                WHERE resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
            ) AS additive_amount,

        SUM(federal_action_obligation)
            FILTER (
                WHERE resolved_accounting_disposition = 'WITHHOLD_UNRESOLVED'
            ) AS withheld_amount,

        SUM(federal_action_obligation)
            FILTER (
                WHERE resolved_accounting_disposition = 'REFERENCE_ONLY'
            ) AS reference_amount

    FROM etl174b_5o_resolved
)
SELECT
    ROUND(COALESCE(excluded_amount, 0), 2) AS exclude_duplicate,
    ROUND(COALESCE(additive_amount, 0), 2) AS include_additive,
    ROUND(COALESCE(withheld_amount, 0), 2) AS withhold_unresolved,
    ROUND(COALESCE(reference_amount, 0), 2) AS reference_only,
    ROUND(COALESCE(unclassified_amount, 0), 2) AS unclassified_review,

    ROUND(
        130991929515.49::numeric
        - COALESCE(unclassified_amount, 0),
        2
    ) AS reduction_in_unclassified_since_5m,

    ROUND(
        100.0
        * (
            130991929515.49::numeric
            - COALESCE(unclassified_amount, 0)
          )
        / 130991929515.49::numeric,
        4
    ) AS pct_reduction_in_unclassified_since_5m
FROM s;


-- ================================================================================================
-- 20. COMPLETION MARKER
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5O PROFILE COMPLETE - POST-VA ASSISTANCE BRIDGE - NO DB WRITES';
END
$$;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5O COMPLETE'
\echo '===================================================================================================='
\echo 'NO DATABASE WRITES'
