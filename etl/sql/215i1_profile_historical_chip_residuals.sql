
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215I1 - HISTORICAL CHIP RESIDUAL EVIDENCE'
\echo 'FY2018-FY2019 / READ ONLY / NO POLICY DECISIONS'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. VERIFY EXACT RESIDUAL POPULATION'

DO $check$
DECLARE
    v_rows bigint;
    v_amount numeric;
    v_all_rows bigint;
    v_all_amount numeric;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation),0)
    INTO v_all_rows, v_all_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.767';

    IF v_all_rows <> 16 OR v_all_amount <> 476425502.00 THEN
        RAISE EXCEPTION
            'BLOCK: CHIP source baseline changed: % rows, %',
            v_all_rows, v_all_amount;
    END IF;

    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation),0)
    INTO v_rows, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.767'
    AND COALESCE(
        NULLIF(BTRIM(award_id_fain),''),
        NULLIF(BTRIM(award_id_uri),'')
    ) NOT IN (
        '1805WA5021', '1905WA5021', '1Y1CMS331701'
    );

    IF v_rows <> 11 OR v_amount <> -19561782.00 THEN
        RAISE EXCEPTION
            'BLOCK: residual baseline changed: % rows, %',
            v_rows, v_amount;
    END IF;

    RAISE NOTICE
        'ETL-215I1 BASELINE PASS: 11 residual rows / -$19561782';
END
$check$;

\echo ''
\echo '2. INDIVIDUAL RESIDUAL TRANSACTIONS'

WITH residual AS (
    SELECT *
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.767'
    AND COALESCE(
        NULLIF(BTRIM(award_id_fain),''),
        NULLIF(BTRIM(award_id_uri),'')
    ) NOT IN (
        '1805WA5021', '1905WA5021', '1Y1CMS331701'
    )
)
SELECT
    action_date_fiscal_year AS fy,
    action_date,
    assistance_transaction_id,
    assistance_transaction_unique_key,
    award_id_fain,
    award_id_uri,
    federal_action_obligation,
    total_outlayed_amount_for_overall_award,
    performance_state_fips,
    performance_county_fips,
    recipient_name,
    funding_agency_name,
    awarding_agency_name
FROM residual
ORDER BY
    award_id_fain,
    action_date,
    assistance_transaction_id;

\echo ''
\echo '3. AWARD-LEVEL SIGNED RECONCILIATION'

WITH residual AS (
    SELECT *
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.767'
    AND COALESCE(
        NULLIF(BTRIM(award_id_fain),''),
        NULLIF(BTRIM(award_id_uri),'')
    ) NOT IN (
        '1805WA5021', '1905WA5021', '1Y1CMS331701'
    )
)
SELECT
    action_date_fiscal_year AS fy,
    award_id_fain,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE federal_action_obligation > 0
    ) AS positive_transactions,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,
    SUM(federal_action_obligation) AS net_obligations,
    SUM(ABS(federal_action_obligation)) AS gross_absolute_activity,
    MIN(action_date) AS first_action_date,
    MAX(action_date) AS last_action_date
FROM residual
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '4. RAW OBSERVATION LINKAGE AND IDENTITY'

WITH residual AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year,
        award_id_fain
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.767'
    AND COALESCE(
        NULLIF(BTRIM(award_id_fain),''),
        NULLIF(BTRIM(award_id_uri),'')
    ) NOT IN (
        '1805WA5021', '1905WA5021', '1Y1CMS331701'
    )
)
SELECT
    r.action_date_fiscal_year AS fy,
    r.award_id_fain,
    r.assistance_transaction_id,
    COUNT(o.raw_assistance_transaction_id)
        AS raw_observation_rows,
    COUNT(o.award_transaction_observation_id)
        AS award_observation_rows,
    STRING_AGG(DISTINCT o.recipient_name, ' | ')
        AS observed_recipient_names,
    STRING_AGG(DISTINCT o.funding_agency_name, ' | ')
        AS observed_funding_agencies,
    STRING_AGG(DISTINCT o.awarding_agency_name, ' | ')
        AS observed_awarding_agencies,
    COUNT(DISTINCT o.recipient_identity_key)
        AS distinct_recipient_identity_keys
FROM residual r
LEFT JOIN analysis.v_assistance_transaction_observation_ledger o
  ON o.assistance_transaction_id = r.assistance_transaction_id
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

\echo ''
\echo '5. CROSS-YEAR AWARD IDENTIFIER CONTEXT'

WITH target_awards AS (
    SELECT DISTINCT BTRIM(award_id_fain) AS award_id
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.767'
    AND COALESCE(
        NULLIF(BTRIM(award_id_fain),''),
        NULLIF(BTRIM(award_id_uri),'')
    ) NOT IN (
        '1805WA5021', '1905WA5021', '1Y1CMS331701'
    )
)
SELECT
    a.action_date_fiscal_year AS fy,
    a.award_id_fain,
    COUNT(*) AS transactions,
    SUM(a.federal_action_obligation) AS net_obligations,
    MIN(a.action_date) AS first_action_date,
    MAX(a.action_date) AS last_action_date
FROM analysis.v_certified_assistance_ledger a
JOIN target_awards t
  ON BTRIM(a.award_id_fain) = t.award_id
WHERE BTRIM(a.cfda_number) = '93.767'
GROUP BY 1, 2
ORDER BY 2, 1;

\echo ''
\echo '6. HISTORICAL CLASSIFICATION COLLISION CHECK'

SELECT
    a.source_award_identifier,
    a.accounting_disposition,
    a.methodology_version,
    a.valid_from_fiscal_year,
    a.valid_through_fiscal_year
FROM reference.federal_inflow_award_classification a
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
  AND a.source_program_code = '93.767'
  AND a.source_award_identifier IN (
      '1805WA5R21',
      '1Z0CMS330855',
      '1005WACPBP',
      '0905WACPBP',
      '1205WACPBP',
      '1105WACPBP'
  )
ORDER BY a.source_award_identifier,
         a.valid_from_fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-215I1 COMPLETE - READ ONLY'
