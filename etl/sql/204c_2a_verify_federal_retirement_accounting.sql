
/*
===============================================================================
ETL-204C-2A
FEDERAL RETIREMENT ACCOUNTING VERIFICATION
Railroad Retirement / RUIA — Washington FY2020–FY2024

READ ONLY — NO DATABASE WRITES

Evidence:
  ETL-189A through ETL-189D
  ETL-190 / ANALYSIS-190-v1

Expected control:
  12,511 transactions
  $1,357,308,008.42 total net obligations

  Railroad Retirement: $1,338,494,529.25
  RUIA:                 $18,813,479.17

This verifies persisted policy and award classifications.
It does not authorize final ledger publication.
===============================================================================
*/

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '=============================================================='
\echo 'ETL-204C-2A — FEDERAL RETIREMENT ACCOUNTING VERIFICATION'
\echo '=============================================================='
\echo ''

-- ------------------------------------------------------------------
-- 1. Verify persisted ETL-190 source policies
-- ------------------------------------------------------------------

\echo 'SECTION 1 — ETL-190 SOURCE POLICIES'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-190-v1'
ORDER BY inflow_family, inflow_subfamily;


-- ------------------------------------------------------------------
-- 2. Verify award-level classification persistence
-- ------------------------------------------------------------------

\echo ''
\echo 'SECTION 2 — AWARD CLASSIFICATION COUNTS'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    COUNT(*) AS classified_awards,
    COUNT(DISTINCT source_award_identifier)
        AS distinct_awards
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '57.001'
  AND methodology_version = 'ANALYSIS-190-v1'
GROUP BY
    inflow_family,
    inflow_subfamily,
    accounting_disposition
ORDER BY inflow_family, inflow_subfamily;


-- ------------------------------------------------------------------
-- 3. Reproduce original assistance control
-- ------------------------------------------------------------------

\echo ''
\echo 'SECTION 3 — ORIGINAL AL 57.001 CONTROL'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    )) AS distinct_awards,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS total_net_obligations,
    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS covid_obligations
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '57.001';


-- ------------------------------------------------------------------
-- 4. Verify award-level coverage and detect classification collisions
-- ------------------------------------------------------------------

\echo ''
\echo 'SECTION 4 — AWARD-LEVEL COVERAGE'

WITH focal AS (
    SELECT
        l.assistance_transaction_id,
        COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger l
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number = '57.001'
),
classification AS (
    SELECT
        source_award_identifier,
        COUNT(*) AS matching_classifications,
        COUNT(*) FILTER (
            WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
        ) AS additive_classifications
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001'
      AND methodology_version = 'ANALYSIS-190-v1'
    GROUP BY source_award_identifier
)
SELECT
    COUNT(*) AS focal_transactions,
    COUNT(*) FILTER (
        WHERE c.matching_classifications = 1
    ) AS exactly_one_classification,
    COUNT(*) FILTER (
        WHERE c.source_award_identifier IS NULL
    ) AS missing_classification,
    COUNT(*) FILTER (
        WHERE c.matching_classifications > 1
    ) AS multiple_classifications,
    COUNT(*) FILTER (
        WHERE c.additive_classifications = 1
          AND c.matching_classifications = 1
    ) AS exactly_one_additive_classification
FROM focal f
LEFT JOIN classification c
  ON c.source_award_identifier = f.award_identifier;


-- ------------------------------------------------------------------
-- 5. Recover classified annual retirement amounts
-- ------------------------------------------------------------------

\echo ''
\echo 'SECTION 5 — ANNUAL CLASSIFIED RETIREMENT AMOUNTS'

WITH classification AS (
    SELECT
        source_award_identifier,
        MIN(inflow_family) AS inflow_family,
        MIN(inflow_subfamily) AS inflow_subfamily,
        MIN(accounting_disposition) AS accounting_disposition,
        COUNT(*) AS classification_count
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001'
      AND methodology_version = 'ANALYSIS-190-v1'
    GROUP BY source_award_identifier
)
SELECT
    l.action_date_fiscal_year AS fiscal_year,
    COALESCE(c.inflow_family, 'UNCLASSIFIED')
        AS inflow_family,
    COALESCE(c.inflow_subfamily, 'UNCLASSIFIED')
        AS inflow_subfamily,
    COALESCE(c.accounting_disposition, 'UNCLASSIFIED')
        AS accounting_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(l.federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(
        CASE WHEN l.is_covid
             THEN l.federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS covid_obligations,
    COUNT(*) FILTER (
        WHERE COALESCE(c.classification_count, 0) <> 1
    ) AS classification_exceptions
FROM analysis.v_certified_assistance_ledger l
LEFT JOIN classification c
  ON c.source_award_identifier = COALESCE(
      NULLIF(l.award_id_fain, ''),
      NULLIF(l.award_id_uri, '')
  )
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.cfda_number = '57.001'
GROUP BY
    l.action_date_fiscal_year,
    c.inflow_family,
    c.inflow_subfamily,
    c.accounting_disposition
ORDER BY
    fiscal_year,
    inflow_family,
    inflow_subfamily;


-- ------------------------------------------------------------------
-- 6. Verify historical control totals
-- ------------------------------------------------------------------

\echo ''
\echo 'SECTION 6 — CONTROL RECONCILIATION'

WITH classified AS (
    SELECT
        l.assistance_transaction_id,
        l.federal_action_obligation,
        a.inflow_family,
        COUNT(a.source_award_identifier) AS match_count
    FROM analysis.v_certified_assistance_ledger l
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = '57.001'
     AND a.methodology_version = 'ANALYSIS-190-v1'
     AND a.source_award_identifier = COALESCE(
         NULLIF(l.award_id_fain, ''),
         NULLIF(l.award_id_uri, '')
     )
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number = '57.001'
    GROUP BY
        l.assistance_transaction_id,
        l.federal_action_obligation,
        a.inflow_family
),
totals AS (
    SELECT
        COUNT(*) AS transaction_count,
        COALESCE(SUM(federal_action_obligation), 0)
            AS total_amount,
        COALESCE(SUM(federal_action_obligation) FILTER (
            WHERE inflow_family = 'RAILROAD_RETIREMENT'
        ), 0) AS retirement_amount,
        COALESCE(SUM(federal_action_obligation) FILTER (
            WHERE inflow_family = 'RAILROAD_SOCIAL_INSURANCE'
        ), 0) AS ruia_amount,
        COUNT(*) FILTER (
            WHERE match_count <> 1
        ) AS classification_exceptions
    FROM classified
)
SELECT
    transaction_count,
    ROUND(total_amount, 2) AS total_amount,
    ROUND(retirement_amount, 2) AS retirement_amount,
    ROUND(ruia_amount, 2) AS ruia_amount,
    classification_exceptions,
    CASE
        WHEN transaction_count = 12511
         AND ROUND(total_amount, 2) = 1357308008.42
         AND ROUND(retirement_amount, 2) = 1338494529.25
         AND ROUND(ruia_amount, 2) = 18813479.17
         AND classification_exceptions = 0
        THEN 'PASS'
        ELSE 'REVIEW_REQUIRED'
    END AS reconciliation_status
FROM totals;

COMMIT;

\echo ''
\echo '=============================================================='
\echo 'ETL-204C-2A COMPLETE — READ ONLY'
\echo '=============================================================='
