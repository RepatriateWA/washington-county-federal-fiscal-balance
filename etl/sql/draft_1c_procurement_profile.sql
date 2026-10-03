\echo ''
\echo '===================================================================================================='
\echo 'WCFFBP DRAFT 1C'
\echo 'STATEWIDE PROCUREMENT ACCOUNTING PROFILE'
\echo 'READ ONLY'
\echo '===================================================================================================='
\echo ''

\set ON_ERROR_STOP on

BEGIN;

-- ================================================================================================
-- 1. CANONICAL PROCUREMENT CONTROL BY FISCAL YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. CANONICAL PROCUREMENT CONTROL BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    fiscal_year,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT award_id) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS net_obligation,
    ROUND(SUM(CASE
        WHEN federal_action_obligation > 0
        THEN federal_action_obligation ELSE 0
    END)::numeric, 2) AS positive_obligation,
    ROUND(SUM(CASE
        WHEN federal_action_obligation < 0
        THEN federal_action_obligation ELSE 0
    END)::numeric, 2) AS negative_obligation
FROM procurement.award_transaction
GROUP BY fiscal_year
ORDER BY fiscal_year;


-- ================================================================================================
-- 2. PROCUREMENT COVERAGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. PROCUREMENT COVERAGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    MIN(fiscal_year) AS first_fiscal_year,
    MAX(fiscal_year) AS last_fiscal_year,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT award_id) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS net_obligation
FROM procurement.award_transaction;


-- ================================================================================================
-- 3. AGENCY TABLE INVENTORY
--
-- Find the actual agency relations rather than guessing their schema.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. PROCUREMENT-RELATED AGENCY RELATIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE
       table_name ILIKE '%agency%'
    OR table_name ILIKE '%subagency%'
ORDER BY
    table_schema,
    table_name;


-- ================================================================================================
-- 4. PROCUREMENT AWARD AGENCY KEYS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. PROCUREMENT AWARD AGENCY KEY COVERAGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS award_count,

    COUNT(*) FILTER (
        WHERE awarding_agency_id IS NOT NULL
    ) AS awards_with_awarding_agency,

    COUNT(*) FILTER (
        WHERE funding_agency_id IS NOT NULL
    ) AS awards_with_funding_agency,

    COUNT(*) FILTER (
        WHERE awarding_subagency_id IS NOT NULL
    ) AS awards_with_awarding_subagency,

    COUNT(*) FILTER (
        WHERE funding_subagency_id IS NOT NULL
    ) AS awards_with_funding_subagency

FROM procurement.award;


-- ================================================================================================
-- 5. PROCUREMENT AWARD AGENCY KEY DISTRIBUTION
--
-- IDs only. This will let us identify the important agencies once we inspect the reference relation.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. FUNDING AGENCY ID DISTRIBUTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    a.funding_agency_id,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT t.award_id) AS award_count,
    ROUND(SUM(t.federal_action_obligation)::numeric, 2) AS net_obligation
FROM procurement.award_transaction t
JOIN procurement.award a
  ON a.award_id = t.award_id
GROUP BY a.funding_agency_id
ORDER BY ABS(SUM(t.federal_action_obligation)) DESC NULLS LAST;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. AWARDING AGENCY ID DISTRIBUTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    a.awarding_agency_id,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT t.award_id) AS award_count,
    ROUND(SUM(t.federal_action_obligation)::numeric, 2) AS net_obligation
FROM procurement.award_transaction t
JOIN procurement.award a
  ON a.award_id = t.award_id
GROUP BY a.awarding_agency_id
ORDER BY ABS(SUM(t.federal_action_obligation)) DESC NULLS LAST;


-- ================================================================================================
-- 7. PROCUREMENT BY FY x FUNDING AGENCY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. PROCUREMENT BY FY x FUNDING AGENCY ID'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    t.fiscal_year,
    a.funding_agency_id,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT t.award_id) AS award_count,
    ROUND(SUM(t.federal_action_obligation)::numeric, 2) AS net_obligation
FROM procurement.award_transaction t
JOIN procurement.award a
  ON a.award_id = t.award_id
GROUP BY
    t.fiscal_year,
    a.funding_agency_id
ORDER BY
    t.fiscal_year,
    ABS(SUM(t.federal_action_obligation)) DESC NULLS LAST;


-- ================================================================================================
-- 8. UNLINKED TRANSACTION FIREWALL
--
-- Every transaction should link to an award before we use award-level agency identity.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TRANSACTION -> AWARD LINKAGE FIREWALL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (
        WHERE a.award_id IS NOT NULL
    ) AS linked_transaction_count,
    COUNT(*) FILTER (
        WHERE a.award_id IS NULL
    ) AS unlinked_transaction_count,

    ROUND(SUM(t.federal_action_obligation)::numeric, 2)
        AS total_net_obligation,

    ROUND(SUM(
        CASE
            WHEN a.award_id IS NULL
            THEN t.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS unlinked_net_obligation

FROM procurement.award_transaction t

LEFT JOIN procurement.award a
  ON a.award_id = t.award_id;


-- ================================================================================================
-- 9. DUPLICATE TRANSACTION-ID FIREWALL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. USASPENDING TRANSACTION-ID UNIQUENESS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT usaspending_transaction_id) AS distinct_transaction_id_count,
    COUNT(*) - COUNT(DISTINCT usaspending_transaction_id) AS duplicate_difference
FROM procurement.award_transaction;


-- ================================================================================================
-- 10. NULL FISCAL YEAR / NULL OBLIGATION FIREWALL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. REQUIRED ACCOUNTING FIELD FIREWALL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) FILTER (
        WHERE fiscal_year IS NULL
    ) AS null_fiscal_year_count,

    COUNT(*) FILTER (
        WHERE federal_action_obligation IS NULL
    ) AS null_obligation_count,

    ROUND(SUM(
        CASE
            WHEN fiscal_year IS NULL
            THEN COALESCE(federal_action_obligation, 0)
            ELSE 0
        END
    )::numeric, 2) AS null_fiscal_year_obligation

FROM procurement.award_transaction;


-- ================================================================================================
-- 11. CLOSURE
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo 'WCFFBP DRAFT 1C PROCUREMENT PROFILE COMPLETE'
\echo ''
\echo 'READ ONLY'
\echo 'No database writes.'
\echo 'No procurement accounting decision.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;