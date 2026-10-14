
-- ============================================================
-- WCFFBP ETL-205
-- HISTORICAL RRB CLASSIFICATION: FY2018-FY2019
-- Methodology: ANALYSIS-205-v1
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN;

-- 1. Historical focal population.
CREATE TEMP TABLE m205_source ON COMMIT DROP AS
SELECT
    assistance_transaction_id,
    action_date_fiscal_year AS fiscal_year,
    federal_action_obligation AS obligation,
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier,
    substring(
        assistance_award_unique_key
        FROM '^ASST_AGG_RRB_[0-9]{6}_[[:space:]"]*([0-9]{4})[[:space:]"]*_'
    ) AS treasury_code
FROM analysis.v_certified_assistance_ledger
WHERE (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
  AND TRIM(cfda_number) = '57.001';

-- 2. Determine historical classification.
CREATE TEMP TABLE m205_payload ON COMMIT DROP AS
SELECT
    *,
    CASE
        WHEN treasury_code IN ('8010','8011','0111')
            THEN 'RAILROAD_RETIREMENT'
        WHEN treasury_code = '8051'
            THEN 'RAILROAD_SOCIAL_INSURANCE'
    END AS inflow_family,
    CASE treasury_code
        WHEN '8010' THEN 'SOCIAL_SECURITY_EQUIVALENT_BENEFIT_ACCOUNT'
        WHEN '8011' THEN 'RAILROAD_RETIREMENT_ACCOUNT'
        WHEN '0111' THEN 'VESTED_DUAL_BENEFIT_ACCOUNT'
        WHEN '8051' THEN 'RUIA_PENDING_SUBACCOUNT_VERIFICATION'
    END AS inflow_subfamily,
    CASE
        WHEN treasury_code IN ('8010','8011','0111')
            THEN 'INCLUDE_ADDITIVE'
        WHEN treasury_code = '8051'
            THEN 'WITHHOLD_UNRESOLVED'
    END AS accounting_disposition
FROM m205_source;

-- 3. Hard controls: source, partition, collisions.
DO $$
DECLARE
    n bigint;
    d bigint;
    a numeric;
    retirement numeric;
    unresolved numeric;
    bad bigint;
BEGIN
    SELECT COUNT(*),
           COUNT(DISTINCT assistance_transaction_id),
           COALESCE(SUM(obligation),0)
    INTO n,d,a
    FROM m205_payload;

    IF n <> 3307 OR d <> 3307
       OR ROUND(a,2) <> 519180042.71 THEN
        RAISE EXCEPTION
          'ETL-205 source control failed: rows %, distinct %, amount %',
          n,d,a;
    END IF;

    SELECT
        COALESCE(SUM(obligation) FILTER (
            WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
        ),0),
        COALESCE(SUM(obligation) FILTER (
            WHERE accounting_disposition = 'WITHHOLD_UNRESOLVED'
        ),0)
    INTO retirement, unresolved
    FROM m205_payload;

    IF ROUND(retirement,2) <> 515006959.71
       OR ROUND(unresolved,2) <> 4173083.00 THEN
        RAISE EXCEPTION
          'ETL-205 partition mismatch: retirement %, unresolved %',
          retirement,unresolved;
    END IF;

    SELECT COUNT(*) INTO bad
    FROM m205_payload
    WHERE treasury_code IS NULL
       OR inflow_family IS NULL
       OR inflow_subfamily IS NULL
       OR accounting_disposition IS NULL
       OR source_award_identifier IS NULL;

    IF bad <> 0 THEN
        RAISE EXCEPTION
          'ETL-205 found % unclassified or unidentified transactions',
          bad;
    END IF;

    SELECT COUNT(*) INTO bad
    FROM (
        SELECT source_award_identifier
        FROM m205_payload
        GROUP BY source_award_identifier
        HAVING COUNT(*) <> 1
    ) q;

    IF bad <> 0 THEN
        RAISE EXCEPTION
          'ETL-205 found % repeated award identifiers',
          bad;
    END IF;

    -- Reject existing classifications, including earlier
    -- ANALYSIS-205-v1 rows. This migration is single-use.
    SELECT COUNT(*) INTO bad
    FROM m205_payload p
    JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = '57.001'
     AND a.source_award_identifier =
         p.source_award_identifier;

    IF bad <> 0 THEN
        RAISE EXCEPTION
          'ETL-205 found % pre-existing award classifications',
          bad;
    END IF;

    SELECT COUNT(*) INTO bad
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001'
      AND methodology_version = 'ANALYSIS-190-v1';

    IF bad <> 12511 THEN
        RAISE EXCEPTION
          'ETL-190 baseline not intact: % classifications',
          bad;
    END IF;

    SELECT COUNT(*) INTO bad
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001';

    IF bad <> 0 THEN
        RAISE EXCEPTION
          'ETL-205 refuses program-level mapping for 57.001';
    END IF;

    RAISE NOTICE 'ETL-205 PRE-MIGRATION CONTROLS PASS';
END $$;

-- 4. Insert historical award classifications.
INSERT INTO reference.federal_inflow_award_classification
(
    source_system,
    source_program_code,
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    'USASPENDING_ASSISTANCE',
    '57.001',
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    'ETL-204C historical RRB reconciliation; official '
    || 'Treasury account-symbol interpretation and '
    || 'FY2019-FY2020 description corroboration. '
    || 'Source measure: net federal action obligation, '
    || 'not independently verified cash expenditure. '
    || 'Codes 8010, 8011 and 0111 are railroad retirement '
    || 'accounts; 8051 remains withheld because the '
    || 'benefit-versus-administrative subaccount is '
    || 'not established. County incidence not certified.',
    'ANALYSIS-205-v1',
    fiscal_year,
    fiscal_year
FROM m205_payload;

-- 5. Effective-resolution validation.
CREATE TEMP TABLE m205_effective ON COMMIT DROP AS
SELECT
    p.assistance_transaction_id,
    p.fiscal_year,
    p.obligation,
    p.treasury_code,
    a.accounting_disposition
FROM m205_payload p
LEFT JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = '57.001'
 AND a.source_award_identifier =
     p.source_award_identifier
 AND a.methodology_version = 'ANALYSIS-205-v1';

SELECT
    fiscal_year,
    treasury_code,
    accounting_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric,2) AS net_obligations
FROM m205_effective
GROUP BY fiscal_year, treasury_code,
         accounting_disposition
ORDER BY fiscal_year, treasury_code;

DO $$
DECLARE
    n bigint;
    d bigint;
    additive numeric;
    withheld numeric;
    bad bigint;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation) FILTER (
            WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
        ),0),
        COALESCE(SUM(obligation) FILTER (
            WHERE accounting_disposition = 'WITHHOLD_UNRESOLVED'
        ),0),
        COUNT(*) FILTER (
            WHERE accounting_disposition IS NULL
        )
    INTO n,d,additive,withheld,bad
    FROM m205_effective;

    IF n <> 3307 OR d <> 3307 OR bad <> 0
       OR ROUND(additive,2) <> 515006959.71
       OR ROUND(withheld,2) <> 4173083.00 THEN
        RAISE EXCEPTION
          'ETL-205 effective resolution failed';
    END IF;

    RAISE NOTICE
      'ETL-205 CERTIFICATION PASS: additive %, withheld %',
      additive, withheld;
END $$;

COMMIT;

\echo 'ETL-205 COMPLETE'
