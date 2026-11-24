
/*
ETL-204C-2B
FY2018–FY2019 RAILROAD RETIREMENT SOURCE DISCOVERY

READ ONLY
No database writes or policy changes.
*/

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '======================================================'
\echo 'ETL-204C-2B — FY2018–FY2019 RAILROAD DISCOVERY'
\echo '======================================================'

-- 1. Certified assistance population by fiscal year

\echo ''
\echo 'SECTION 1 — FY2018–FY2019 ASSISTANCE COVERAGE'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    )) AS distinct_awards,
    ROUND(
        SUM(federal_action_obligation)::numeric, 2
    ) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2018 AND 2019
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;


-- 2. Railroad retirement population

\echo ''
\echo 'SECTION 2 — AL 57.001 RAILROAD TRANSACTIONS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    )) AS distinct_awards,
    ROUND(
        SUM(federal_action_obligation)::numeric, 2
    ) AS net_obligations,
    COUNT(*) FILTER (
        WHERE NULLIF(
            TRIM(canonical_award_description), ''
        ) IS NOT NULL
    ) AS described_transactions
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2018 AND 2019
  AND cfda_number = '57.001'
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;


-- 3. Existing source policies and year coverage

\echo ''
\echo 'SECTION 3 — EXISTING RAILROAD POLICIES'

SELECT
    inflow_family,
    inflow_subfamily,
    preferred_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-190-v1'
ORDER BY inflow_family, inflow_subfamily;


-- 4. Earlier-year award-level classification coverage

\echo ''
\echo 'SECTION 4 — EARLIER-YEAR AWARD CLASSIFICATIONS'

WITH focal AS (
    SELECT
        l.action_date_fiscal_year,
        COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger l
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2018 AND 2019
      AND l.cfda_number = '57.001'
),
classification AS (
    SELECT
        source_award_identifier,
        COUNT(*) AS classification_count
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001'
    GROUP BY source_award_identifier
)
SELECT
    f.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE c.classification_count = 1
    ) AS classified_once,
    COUNT(*) FILTER (
        WHERE c.classification_count IS NULL
    ) AS unclassified,
    COUNT(*) FILTER (
        WHERE c.classification_count > 1
    ) AS classification_collisions
FROM focal f
LEFT JOIN classification c
  ON c.source_award_identifier = f.award_identifier
GROUP BY f.action_date_fiscal_year
ORDER BY fiscal_year;

COMMIT;

\echo ''
\echo 'ETL-204C-2B COMPLETE — READ ONLY'
