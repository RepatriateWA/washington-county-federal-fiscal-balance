
-- ============================================================
-- WCFFBP ETL-204C-2C.2
-- FY2018-FY2019 RAILROAD SEMANTIC PARTITION
-- Reproduces ETL-190 description rules
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

WITH source_rows AS (
    SELECT
        v.assistance_transaction_id,
        v.action_date_fiscal_year AS fiscal_year,
        v.federal_action_obligation AS obligation,
        v.assistance_award_unique_key AS award_key,
        v.canonical_award_description,
        r.raw_record ->> 'transaction_description'
            AS raw_transaction_description,
        r.raw_record ->> 'prime_award_base_transaction_description'
            AS raw_base_description
    FROM analysis.v_certified_assistance_ledger v
    JOIN assistance.award_transaction_observation o
      ON o.assistance_transaction_id =
         v.assistance_transaction_id
    JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         o.raw_assistance_transaction_id
    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
),
descriptions AS (
    SELECT
        *,
        UPPER(COALESCE(
            NULLIF(TRIM(canonical_award_description), ''),
            NULLIF(TRIM(raw_transaction_description), ''),
            NULLIF(TRIM(raw_base_description), ''),
            ''
        )) AS description
    FROM source_rows
),
classified AS (
    SELECT
        *,
        CASE
            WHEN description LIKE
                '%PENSION PAID FROM THE SOCIAL SECURITY EQUIVALENT ACCOUNT%'
                THEN 'RR_RETIREMENT_SSEB_ACCOUNT'
            WHEN description LIKE
                '%PENSION PAID FROM THE RAILROAD RETIREMENT ACCOUNT%'
                THEN 'RR_RETIREMENT_ACCOUNT'
            WHEN description LIKE
                '%PENSION PAID FROM THE VESTED DUAL BENEFIT ACCOUNT%'
                THEN 'RR_VESTED_DUAL_BENEFIT_ACCOUNT'
            WHEN description LIKE
                '%RAILROAD RETIREMENT ACT PENSION RECIPIENT%'
                THEN 'RR_RETIREMENT_PENSION_RECIPIENT'
            WHEN description LIKE
                '%SUPPLEMENTAL FUNDING FOR THE CARES ACT%'
                THEN 'RUIA_COVID_SUPPLEMENTAL_FUNDING'
            WHEN description LIKE '%ENHANCED BENEFIT%'
             AND (
                description LIKE '%CARES%'
                OR description LIKE '%CARWA%'
                OR description LIKE '%AMERICAN RESCUE PLAN%'
                OR description LIKE '%ARPA%'
             )
                THEN 'RUIA_COVID_ENHANCED_BENEFIT'
            WHEN description LIKE '%EXTENDED%'
             AND description LIKE '%BENEFIT%'
             AND (
                description LIKE '%CARES%'
                OR description LIKE '%CARWA%'
                OR description LIKE '%AMERICAN RESCUE PLAN%'
                OR description LIKE '%ARPA%'
             )
                THEN 'RUIA_COVID_EXTENDED_BENEFIT'
            WHEN description LIKE '%WAITING PERIOD%'
             AND (
                description LIKE '%CARES%'
                OR description LIKE '%CARWA%'
                OR description LIKE '%AMERICAN RESCUE PLAN%'
                OR description LIKE '%ARPA%'
             )
                THEN 'RUIA_COVID_WAITING_PERIOD_WAIVER'
            WHEN description LIKE
                '%RAILROAD UNEMPLOYMENT INSURANCE TRUST FUND BENEFIT PAYMENTS%'
                THEN 'RUIA_TRUST_FUND_BENEFITS'
            WHEN description LIKE
                '%RAILROAD UNEMPLOYMENT INSURANCE ACT BENEFIT CLAIMANT%'
                THEN 'RUIA_BENEFIT_CLAIMANT'
            ELSE 'UNCLASSIFIED_REVIEW'
        END AS accounting_partition
    FROM descriptions
)
SELECT
    fiscal_year,
    accounting_partition,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(*) FILTER (
        WHERE description = ''
    ) AS missing_descriptions,
    SUM(obligation) AS net_obligations
FROM classified
GROUP BY fiscal_year, accounting_partition
ORDER BY fiscal_year, accounting_partition;

-- Separate missing-description diagnostic.
SELECT
    v.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE NULLIF(TRIM(v.canonical_award_description), '')
              IS NULL
    ) AS missing_canonical_description,
    COUNT(*) FILTER (
        WHERE NULLIF(TRIM(r.raw_record ->>
              'transaction_description'), '') IS NULL
    ) AS missing_raw_transaction_description,
    COUNT(*) FILTER (
        WHERE NULLIF(TRIM(r.raw_record ->>
              'prime_award_base_transaction_description'), '') IS NULL
    ) AS missing_raw_base_description
FROM analysis.v_certified_assistance_ledger v
JOIN assistance.award_transaction_observation o
  ON o.assistance_transaction_id = v.assistance_transaction_id
JOIN assistance.raw_award_transaction r
  ON r.raw_assistance_transaction_id =
     o.raw_assistance_transaction_id
WHERE v.load_batch_id IN (20, 21)
  AND TRIM(v.cfda_number) = '57.001'
GROUP BY v.action_date_fiscal_year
ORDER BY fiscal_year;

COMMIT;

SELECT 'ETL-204C-2C.2 COMPLETE - NO DATABASE WRITES';
