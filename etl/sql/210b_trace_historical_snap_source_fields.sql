-- ============================================================
-- WCFFBP ETL-210B
-- HISTORICAL SNAP RAW-TO-NORMALIZED PROVENANCE TRACE
-- FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210B - HISTORICAL SNAP SOURCE PROVENANCE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. Raw and normalized linkage integrity
-- ============================================================

\echo ''
\echo '1. SNAP RAW / NORMALIZED LINKAGE'

WITH snap AS (
    SELECT
        assistance_transaction_id,
        load_batch_id,
        source_row_number,
        action_date_fiscal_year,
        federal_action_obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      )
)
SELECT
    s.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT s.assistance_transaction_id)
        AS distinct_certified_transactions,
    COUNT(r.raw_assistance_transaction_id)
        AS raw_matches,
    COUNT(t.assistance_transaction_id)
        AS normalized_matches,
    COUNT(*) FILTER (
        WHERE r.raw_record IS NOT NULL
    ) AS raw_json_present,
    ROUND(SUM(s.federal_action_obligation)::numeric, 2)
        AS joined_net_obligations
FROM snap s
LEFT JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = s.load_batch_id
 AND r.source_row_number = s.source_row_number
LEFT JOIN assistance.award_transaction t
  ON t.assistance_transaction_id =
     s.assistance_transaction_id
GROUP BY s.action_date_fiscal_year
ORDER BY fiscal_year;


-- ============================================================
-- 2. Raw JSON field inventory
-- Only keys relevant to recipient, agency, geography,
-- award identity, and program classification.
-- ============================================================

\echo ''
\echo '2. HISTORICAL SNAP RAW JSON FIELD INVENTORY'

WITH snap AS (
    SELECT load_batch_id, source_row_number
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      )
),
raw_rows AS (
    SELECT r.raw_record
    FROM snap s
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = s.load_batch_id
     AND r.source_row_number = s.source_row_number
),
fields AS (
    SELECT
        e.key,
        e.value
    FROM raw_rows r
    CROSS JOIN LATERAL
        jsonb_each_text(r.raw_record) AS e(key, value)
    WHERE
           e.key ILIKE '%recipient%'
        OR e.key ILIKE '%agency%'
        OR e.key ILIKE '%place%'
        OR e.key ILIKE '%county%'
        OR e.key ILIKE '%state%'
        OR e.key ILIKE '%award%'
        OR e.key ILIKE '%cfda%'
        OR e.key ILIKE '%assistance_listing%'
)
SELECT
    key AS raw_json_key,
    COUNT(*) AS field_occurrences,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(value), '') IS NOT NULL
          AND LOWER(BTRIM(value)) NOT IN (
              'null', 'none', 'nan'
          )
    ) AS populated_occurrences,
    LEFT(
        MIN(NULLIF(BTRIM(value), '')),
        160
    ) AS example_nonempty_value
FROM fields
GROUP BY key
ORDER BY key;


-- ============================================================
-- 3. Normalized and award-level foreign keys
-- ============================================================

\echo ''
\echo '3. NORMALIZED TRANSACTION AND AWARD LINKAGE'

WITH snap AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year,
        assistance_award_id,
        federal_action_obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      )
)
SELECT
    s.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE t.recipient_id IS NOT NULL
    ) AS transaction_recipient_ids,
    COUNT(*) FILTER (
        WHERE t.place_of_performance_id IS NOT NULL
    ) AS transaction_place_ids,
    COUNT(*) FILTER (
        WHERE t.awarding_agency_id IS NOT NULL
    ) AS transaction_awarding_agency_ids,
    COUNT(*) FILTER (
        WHERE t.funding_agency_id IS NOT NULL
    ) AS transaction_funding_agency_ids,
    COUNT(*) FILTER (
        WHERE a.recipient_id IS NOT NULL
    ) AS award_recipient_ids,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(a.canonical_recipient_name), '')
              IS NOT NULL
    ) AS award_recipient_names,
    COUNT(*) FILTER (
        WHERE a.awarding_agency_id IS NOT NULL
    ) AS award_awarding_agency_ids,
    COUNT(*) FILTER (
        WHERE a.funding_agency_id IS NOT NULL
    ) AS award_funding_agency_ids
FROM snap s
LEFT JOIN assistance.award_transaction t
  ON t.assistance_transaction_id =
     s.assistance_transaction_id
LEFT JOIN assistance.award a
  ON a.assistance_award_id = s.assistance_award_id
GROUP BY s.action_date_fiscal_year
ORDER BY fiscal_year;


-- ============================================================
-- 4. Raw record structural inspection
-- ============================================================

\echo ''
\echo '4. RAW JSON STRUCTURE'

WITH snap AS (
    SELECT
        assistance_transaction_id,
        load_batch_id,
        source_row_number,
        action_date_fiscal_year
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      )
)
SELECT
    s.action_date_fiscal_year AS fiscal_year,
    s.assistance_transaction_id,
    s.source_row_number,
    jsonb_typeof(r.raw_record) AS json_structure,
    CASE
        WHEN jsonb_typeof(r.raw_record) = 'object'
        THEN jsonb_object_length_placeholder.key_count
        ELSE NULL
    END AS top_level_keys
FROM snap s
LEFT JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = s.load_batch_id
 AND r.source_row_number = s.source_row_number
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS key_count
    FROM jsonb_object_keys(
        CASE
            WHEN jsonb_typeof(r.raw_record) = 'object'
            THEN r.raw_record
            ELSE '{}'::jsonb
        END
    ) AS k
) AS jsonb_object_length_placeholder ON TRUE
ORDER BY fiscal_year, s.source_row_number
LIMIT 30;


-- ============================================================
-- 5. Historical control assertion
-- ============================================================

\echo ''
\echo '5. HISTORICAL CONTROL ASSERTION'

DO $$
DECLARE
    v_rows bigint;
    v_net numeric;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_rows, v_net
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    IF v_rows <> 27
       OR ROUND(v_net, 2) <> 2461253053.11
    THEN
        RAISE EXCEPTION
            'ETL-210B control failed: rows %, net %',
            v_rows, v_net;
    END IF;

    RAISE NOTICE
        'ETL-210B PASS: 27 SNAP transactions, $2461253053.11 net obligations';
END $$;

COMMIT;

\echo 'ETL-210B COMPLETE - READ ONLY'