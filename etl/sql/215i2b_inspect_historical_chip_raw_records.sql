
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215I2B - HISTORICAL CHIP ORIGINAL SOURCE RECORDS'
\echo 'FY2018-FY2019 / READ ONLY / NO POLICY CHANGES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. EXACT SOURCE LINKAGE CONTROLS'

DO $check$
DECLARE
    v_count bigint;
    v_distinct bigint;
    v_amount numeric;
    v_missing bigint;
BEGIN
    WITH target AS (
        SELECT
            a.assistance_transaction_id,
            a.federal_action_obligation
        FROM analysis.v_certified_assistance_ledger a
        WHERE (
            (a.load_batch_id = 20
             AND a.action_date_fiscal_year = 2018)
            OR
            (a.load_batch_id = 21
             AND a.action_date_fiscal_year = 2019)
        )
          AND BTRIM(a.cfda_number) = '93.767'
          AND a.award_id_fain IN (
              '1805WA5R21',
              '1Z0CMS330855',
              '0905WACPBP',
              '1005WACPBP',
              '1105WACPBP',
              '1205WACPBP'
          )
    )
    SELECT
        COUNT(*),
        COUNT(DISTINCT t.assistance_transaction_id),
        COALESCE(SUM(t.federal_action_obligation),0),
        COUNT(*) FILTER (
            WHERE r.raw_assistance_transaction_id IS NULL
        )
    INTO v_count, v_distinct, v_amount, v_missing
    FROM target t
    LEFT JOIN assistance.award_transaction_observation o
      ON o.assistance_transaction_id =
         t.assistance_transaction_id
    LEFT JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         o.raw_assistance_transaction_id;

    IF v_count <> 11
       OR v_distinct <> 11
       OR v_amount <> -19561782.00
       OR v_missing <> 0
    THEN
        RAISE EXCEPTION
            'BLOCK: rows %, distinct %, amount %, missing %',
            v_count, v_distinct, v_amount, v_missing;
    END IF;

    RAISE NOTICE
        'ETL-215I2B LINKAGE PASS: 11 distinct raw observations';
END
$check$;

\echo ''
\echo '2. RAW JSON FIELD INVENTORY'

WITH target AS (
    SELECT a.assistance_transaction_id
    FROM analysis.v_certified_assistance_ledger a
    WHERE (
        (a.load_batch_id = 20
         AND a.action_date_fiscal_year = 2018)
        OR
        (a.load_batch_id = 21
         AND a.action_date_fiscal_year = 2019)
    )
      AND BTRIM(a.cfda_number) = '93.767'
      AND a.award_id_fain IN (
          '1805WA5R21',
          '1Z0CMS330855',
          '0905WACPBP',
          '1005WACPBP',
          '1105WACPBP',
          '1205WACPBP'
      )
)
SELECT
    k.key AS original_source_field,
    COUNT(*) AS observations_with_field,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(k.value), '') IS NOT NULL
          AND UPPER(BTRIM(k.value)) NOT IN (
              'NULL', 'NONE', 'N/A'
          )
    ) AS populated_observations,
    MAX(LEFT(k.value, 110)) FILTER (
        WHERE NULLIF(BTRIM(k.value), '') IS NOT NULL
    ) AS example_value
FROM target t
JOIN assistance.award_transaction_observation o
  ON o.assistance_transaction_id =
     t.assistance_transaction_id
JOIN assistance.raw_award_transaction r
  ON r.raw_assistance_transaction_id =
     o.raw_assistance_transaction_id
CROSS JOIN LATERAL jsonb_each_text(r.raw_record)
    AS k(key, value)
GROUP BY k.key
ORDER BY k.key;

\echo ''
\echo '3. TRANSACTION-LEVEL RAW PROVENANCE FIELDS'

WITH target AS (
    SELECT
        a.assistance_transaction_id,
        a.action_date_fiscal_year AS fy,
        a.action_date,
        a.award_id_fain,
        a.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger a
    WHERE (
        (a.load_batch_id = 20
         AND a.action_date_fiscal_year = 2018)
        OR
        (a.load_batch_id = 21
         AND a.action_date_fiscal_year = 2019)
    )
      AND BTRIM(a.cfda_number) = '93.767'
      AND a.award_id_fain IN (
          '1805WA5R21',
          '1Z0CMS330855',
          '0905WACPBP',
          '1005WACPBP',
          '1105WACPBP',
          '1205WACPBP'
      )
)
SELECT
    t.fy,
    t.award_id_fain,
    t.assistance_transaction_id,
    t.action_date,
    t.federal_action_obligation,
    r.raw_assistance_transaction_id,
    r.load_batch_id AS raw_load_batch_id,
    r.source_row_number AS raw_source_row_number,
    k.key AS original_source_field,
    LEFT(k.value, 1000) AS original_source_value
FROM target t
JOIN assistance.award_transaction_observation o
  ON o.assistance_transaction_id =
     t.assistance_transaction_id
JOIN assistance.raw_award_transaction r
  ON r.raw_assistance_transaction_id =
     o.raw_assistance_transaction_id
CROSS JOIN LATERAL jsonb_each_text(r.raw_record)
    AS k(key, value)
WHERE k.key ~* (
    'descri|modif|reason|purpose|adjust|amend|'
    || 'award|recipient|agency|account|obligat|'
    || 'outlay|action|date|period|program|'
    || 'cfda|fain|uri|state|place|transaction'
)
  AND NULLIF(BTRIM(k.value), '') IS NOT NULL
  AND UPPER(BTRIM(k.value)) NOT IN ('NULL', 'NONE', 'N/A')
ORDER BY
    t.award_id_fain,
    t.action_date,
    t.assistance_transaction_id,
    k.key;

\echo ''
\echo '4. CANONICAL DESCRIPTIONS AND MODIFICATION DATA'

SELECT
    a.action_date_fiscal_year AS fy,
    a.award_id_fain,
    a.assistance_transaction_id,
    a.action_date,
    a.modification_number,
    a.action_type_code,
    a.transaction_description,
    a.canonical_award_description,
    a.award_first_action_date,
    a.award_last_action_date,
    a.last_modified_date,
    a.federal_action_obligation
FROM analysis.v_assistance_transaction_observation_ledger a
WHERE (
    (a.load_batch_id = 20
     AND a.action_date_fiscal_year = 2018)
    OR
    (a.load_batch_id = 21
     AND a.action_date_fiscal_year = 2019)
)
  AND BTRIM(a.cfda_number) = '93.767'
  AND a.award_id_fain IN (
      '1805WA5R21',
      '1Z0CMS330855',
      '0905WACPBP',
      '1005WACPBP',
      '1105WACPBP',
      '1205WACPBP'
  )
ORDER BY
    a.award_id_fain,
    a.action_date,
    a.assistance_transaction_id;

ROLLBACK;

\echo ''
\echo 'ETL-215I2B COMPLETE - READ ONLY'
