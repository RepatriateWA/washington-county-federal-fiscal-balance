
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215G - HISTORICAL CHIP / MEDICARE POLICY PREFLIGHT'
\echo 'FY2018-FY2019 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. FAIL-CLOSED SOURCE AND POLICY CONTROLS'

DO $verify$
DECLARE
    v_bad integer;
    v_count bigint;
    v_amount numeric;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.767';

    IF v_count <> 16 OR v_amount <> 476425502.00 THEN
        RAISE EXCEPTION
            'FAIL CHIP source: count %, amount %',
            v_count, v_amount;
    END IF;

    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.770';

    IF v_count <> 16 OR v_amount <> 315496326.00 THEN
        RAISE EXCEPTION
            'FAIL Medicare source: count %, amount %',
            v_count, v_amount;
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN ('93.767', '93.770')
      AND valid_from_fiscal_year <= 2019
      AND valid_through_fiscal_year >= 2018;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'FAIL: % existing historical program mappings',
            v_bad;
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN ('93.767', '93.770')
      AND valid_from_fiscal_year <= 2019
      AND valid_through_fiscal_year >= 2018;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'FAIL: % existing historical award classifications',
            v_bad;
    END IF;

    RAISE NOTICE
        'ETL-215G SOURCE AND HISTORICAL POLICY PREFLIGHT PASS';
END
$verify$;

\echo ''
\echo '2. ALL 32 HISTORICAL TRANSACTIONS'

SELECT
    a.action_date_fiscal_year AS fiscal_year,
    BTRIM(a.cfda_number) AS program_code,
    a.assistance_transaction_id,
    a.action_date,
    COALESCE(
        NULLIF(BTRIM(a.award_id_fain), ''),
        NULLIF(BTRIM(a.award_id_uri), '')
    ) AS award_identifier,
    a.federal_action_obligation AS obligation,
    a.recipient_name AS normalized_recipient,
    a.funding_agency_name AS normalized_funding_agency,
    a.awarding_agency_name AS normalized_awarding_agency,
    CASE
        WHEN BTRIM(a.cfda_number) = '93.767'
         AND COALESCE(
             NULLIF(BTRIM(a.award_id_fain), ''),
             NULLIF(BTRIM(a.award_id_uri), '')
         ) ~ '^[0-9]{2}05WA5021$'
            THEN 'CHIP_CORE_PATTERN_CANDIDATE'
        WHEN BTRIM(a.cfda_number) = '93.767'
         AND COALESCE(
             NULLIF(BTRIM(a.award_id_fain), ''),
             NULLIF(BTRIM(a.award_id_uri), '')
         ) = '1Y1CMS331701'
            THEN 'CHIP_DISTINCT_AWARD_PRECEDENT'
        WHEN BTRIM(a.cfda_number) = '93.767'
            THEN 'CHIP_OTHER_REVIEW'
        WHEN BTRIM(a.cfda_number) = '93.770'
            THEN 'MEDICARE_PARTD_AGGREGATE_CANDIDATE'
    END AS evidence_group
FROM analysis.v_certified_assistance_ledger a
WHERE (
    (a.load_batch_id = 20 AND a.action_date_fiscal_year = 2018)
    OR
    (a.load_batch_id = 21 AND a.action_date_fiscal_year = 2019)
)
AND BTRIM(a.cfda_number) IN ('93.767', '93.770')
ORDER BY
    program_code,
    fiscal_year,
    award_identifier,
    action_date,
    assistance_transaction_id;

\echo ''
\echo '3. RAW OBSERVATION PROVENANCE BY AWARD'

WITH target AS (
    SELECT
        a.assistance_transaction_id,
        a.action_date_fiscal_year AS fiscal_year,
        BTRIM(a.cfda_number) AS program_code,
        COALESCE(
            NULLIF(BTRIM(a.award_id_fain), ''),
            NULLIF(BTRIM(a.award_id_uri), '')
        ) AS award_identifier,
        a.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger a
    WHERE (
        (a.load_batch_id = 20 AND a.action_date_fiscal_year = 2018)
        OR
        (a.load_batch_id = 21 AND a.action_date_fiscal_year = 2019)
    )
    AND BTRIM(a.cfda_number) IN ('93.767', '93.770')
),
observations AS (
    SELECT
        t.*,
        o.raw_assistance_transaction_id,
        o.award_transaction_observation_id,
        o.recipient_name,
        o.funding_agency_name,
        o.awarding_agency_name
    FROM target t
    LEFT JOIN analysis.v_assistance_transaction_observation_ledger o
      ON o.assistance_transaction_id = t.assistance_transaction_id
)
SELECT
    fiscal_year,
    program_code,
    award_identifier,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(*) AS joined_observation_rows,
    COUNT(*) FILTER (
        WHERE raw_assistance_transaction_id IS NOT NULL
    ) AS raw_observation_rows,
    COUNT(*) FILTER (
        WHERE award_transaction_observation_id IS NOT NULL
    ) AS award_observation_rows,
    STRING_AGG(
        DISTINCT NULLIF(BTRIM(recipient_name), ''),
        '; '
    ) AS observed_recipients,
    STRING_AGG(
        DISTINCT NULLIF(BTRIM(funding_agency_name), ''),
        '; '
    ) AS observed_funding_agencies,
    STRING_AGG(
        DISTINCT NULLIF(BTRIM(awarding_agency_name), ''),
        '; '
    ) AS observed_awarding_agencies,
    ROUND(
        SUM(obligation)::numeric, 2
    ) AS observation_join_net_obligations
FROM observations
GROUP BY fiscal_year, program_code, award_identifier
ORDER BY program_code, fiscal_year, award_identifier;

\echo ''
\echo '4. HISTORICAL AWARD PATTERN SUMMARY'

WITH target AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        BTRIM(cfda_number) AS program_code,
        COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), '')
        ) AS award_identifier,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) IN ('93.767', '93.770')
),
grouped AS (
    SELECT *,
        CASE
            WHEN program_code = '93.767'
             AND award_identifier ~ '^[0-9]{2}05WA5021$'
                THEN 'CHIP_CORE_PATTERN_CANDIDATE'
            WHEN program_code = '93.767'
             AND award_identifier = '1Y1CMS331701'
                THEN 'CHIP_DISTINCT_AWARD_PRECEDENT'
            WHEN program_code = '93.767'
                THEN 'CHIP_OTHER_REVIEW'
            ELSE 'MEDICARE_PARTD_AGGREGATE_CANDIDATE'
        END AS evidence_group
    FROM target
)
SELECT
    program_code,
    evidence_group,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_identifier) AS distinct_awards,
    COUNT(*) FILTER (WHERE obligation < 0)
        AS negative_transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS absolute_activity
FROM grouped
GROUP BY program_code, evidence_group
ORDER BY program_code, evidence_group;

\echo ''
\echo '5. EXISTING PRECEDENTS: COMPACT POLICY INVENTORY'

SELECT
    source_program_code,
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.767'
ORDER BY source_award_identifier;

SELECT
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.770'
ORDER BY valid_from_fiscal_year;

\echo ''
\echo '6. MEDICARE AGGREGATE IDENTIFIER STRUCTURE'

WITH target AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), '')
        ) AS award_identifier,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) = '93.770'
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE award_identifier LIKE '%93770%'
    ) AS identifiers_containing_program_code,
    COUNT(*) FILTER (
        WHERE award_identifier LIKE '%-WA-%'
    ) AS identifiers_containing_wa,
    COUNT(*) FILTER (
        WHERE award_identifier LIKE '%-033-%'
    ) AS identifiers_with_033,
    COUNT(*) FILTER (
        WHERE award_identifier LIKE '%-061-%'
    ) AS identifiers_with_061,
    COUNT(DISTINCT award_identifier) AS distinct_identifiers,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM target
GROUP BY fiscal_year
ORDER BY fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-215G COMPLETE - READ ONLY'
