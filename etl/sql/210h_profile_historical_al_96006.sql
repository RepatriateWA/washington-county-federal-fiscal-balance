-- ============================================================
-- WCFFBP ETL-210H
-- HISTORICAL AL 96.006 SOURCE AND PROVENANCE PROFILE
-- FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210H - AL 96.006 HISTORICAL PROFILE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- 1. Transaction totals by fiscal year

\echo ''
\echo '1. SOURCE POPULATION'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(federal_action_obligation))::numeric, 2)
        AS gross_absolute_obligations,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,
    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '96.006'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;


-- 2. Award identifier profile

\echo ''
\echo '2. AWARD IDENTIFIER PROFILE'

WITH source AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), ''),
            '[MISSING]'
        ) AS award_identifier,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '96.006'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    award_identifier,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM source
GROUP BY fiscal_year, award_identifier
ORDER BY fiscal_year, net_obligations DESC
LIMIT 40;


-- 3. Raw source-field inventory

\echo ''
\echo '3. RAW JSON SOURCE FIELD INVENTORY'

WITH raw_source AS (
    SELECT r.raw_record
    FROM assistance.raw_award_transaction r
    JOIN analysis.v_certified_assistance_ledger c
      ON c.load_batch_id = r.load_batch_id
     AND c.source_row_number = r.source_row_number
    WHERE BTRIM(c.cfda_number) = '96.006'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    k.key AS source_field,
    COUNT(*) AS records_with_field,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(r.raw_record ->> k.key), '')
              IS NOT NULL
    ) AS populated_records,
    LEFT(
        MIN(NULLIF(BTRIM(r.raw_record ->> k.key), '')),
        140
    ) AS example_value
FROM raw_source r
CROSS JOIN LATERAL jsonb_object_keys(r.raw_record)
    AS k(key)
WHERE
       k.key ILIKE '%agency%'
    OR k.key ILIKE '%recipient%'
    OR k.key ILIKE '%description%'
    OR k.key ILIKE '%award%'
    OR k.key ILIKE '%performance%'
    OR k.key ILIKE '%cfda%'
    OR k.key ILIKE '%state%'
    OR k.key ILIKE '%county%'
GROUP BY k.key
ORDER BY k.key;


-- 4. Descriptions, agencies, and recipients

\echo ''
\echo '4. PRINCIPAL SOURCE IDENTITIES'

WITH source AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        c.federal_action_obligation AS obligation,
        r.raw_record
    FROM assistance.raw_award_transaction r
    JOIN analysis.v_certified_assistance_ledger c
      ON c.load_batch_id = r.load_batch_id
     AND c.source_row_number = r.source_row_number
    WHERE BTRIM(c.cfda_number) = '96.006'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    COALESCE(
        NULLIF(raw_record ->> 'cfda_title', ''),
        '[MISSING]'
    ) AS program_title,
    COALESCE(
        NULLIF(raw_record ->> 'awarding_agency_name', ''),
        '[MISSING]'
    ) AS awarding_agency,
    COALESCE(
        NULLIF(raw_record ->> 'funding_agency_name', ''),
        '[MISSING]'
    ) AS funding_agency,
    COALESCE(
        NULLIF(raw_record ->> 'recipient_name', ''),
        '[MISSING]'
    ) AS recipient_name,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM source
GROUP BY
    fiscal_year,
    program_title,
    awarding_agency,
    funding_agency,
    recipient_name
ORDER BY net_obligations DESC
LIMIT 40;


-- 5. Existing accounting policy evidence

\echo ''
\echo '5. EXISTING AL 96.006 PROGRAM MAPPINGS'

SELECT
    p.federal_inflow_program_policy_mapping_id,
    p.source_system,
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.overlapping_sources,
    s.ledger_treatment,
    s.source_selection_basis
FROM reference.federal_inflow_program_policy_mapping p
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code = '96.006'
ORDER BY p.valid_from_fiscal_year;


-- 6. Automated source controls

\echo ''
\echo '6. AUTOMATED SOURCE CONTROLS'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_raw_matches bigint;
    v_raw_distinct bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_rows, v_distinct, v_net
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '96.006'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    SELECT
        COUNT(*),
        COUNT(DISTINCT c.assistance_transaction_id)
    INTO v_raw_matches, v_raw_distinct
    FROM analysis.v_certified_assistance_ledger c
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) = '96.006'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      );

    IF v_rows <> 1658
       OR v_distinct <> 1658
       OR ROUND(v_net, 2) <> 2084260846.00
       OR v_raw_matches <> 1658
       OR v_raw_distinct <> 1658
    THEN
        RAISE EXCEPTION
            'ETL-210H source mismatch: rows %, distinct %, net %, raw matches %, raw distinct %',
            v_rows,
            v_distinct,
            v_net,
            v_raw_matches,
            v_raw_distinct;
    END IF;

    RAISE NOTICE
        'ETL-210H PASS: 1658 AL 96.006 transactions, $2084260846.00 net, complete raw-source linkage';

END $$;

COMMIT;

\echo 'ETL-210H COMPLETE - READ ONLY'