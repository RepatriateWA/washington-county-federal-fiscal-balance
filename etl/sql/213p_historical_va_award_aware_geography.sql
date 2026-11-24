
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213P v0.1 - AWARD-AWARE GEOGRAPHIC EVIDENCE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Geographic evidence indicators by fiscal year'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.federal_action_obligation AS obligation,
        COALESCE(t.transaction_description, '') AS tx_text,
        COALESCE(a.award_description, '') AS award_text
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
),
flags AS (
    SELECT *,
        (
            tx_text || ' ' || award_text
        ) ~* (
            'nationwide|nationally|national scope|' ||
            'fifty[[:space:]]*\(50\)[[:space:]]*united states|' ||
            'all[[:space:]]*50[[:space:]]*states|' ||
            'throughout[[:space:]]+the[[:space:]]+united states'
        ) AS nationwide_evidence,
        (
            tx_text || ' ' || award_text
        ) ~* (
            'white city|oregon|multi-state|multistate|' ||
            'multiple states|across states'
        ) AS multistate_evidence,
        (
            tx_text || ' ' || award_text
        ) ~* (
            'seattle|spokane|walla walla|vancouver, wa|' ||
            'tacoma|american lake|mann-grandstaff'
        ) AS named_wa_evidence
    FROM va
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS total_net_obligations,
    COUNT(*) FILTER (WHERE nationwide_evidence)
        AS nationwide_count,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE nationwide_evidence
    ), 0), 2) AS nationwide_net,
    COUNT(*) FILTER (WHERE multistate_evidence)
        AS multistate_count,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE multistate_evidence
    ), 0), 2) AS multistate_net,
    COUNT(*) FILTER (WHERE named_wa_evidence)
        AS named_wa_count,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE named_wa_evidence
    ), 0), 2) AS named_wa_net,
    COUNT(*) FILTER (
        WHERE NOT nationwide_evidence
          AND NOT multistate_evidence
          AND NOT named_wa_evidence
    ) AS no_keyword_evidence_count
FROM flags
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. Known nationwide contract: complete award controls'

SELECT
    t.fiscal_year,
    a.piid,
    COUNT(*) AS transactions,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS net_obligations,
    BOOL_OR(
        COALESCE(t.transaction_description, '') ~*
        'fifty[[:space:]]*\(50\)[[:space:]]*united states'
    ) AS transaction_text_match,
    BOOL_OR(
        COALESCE(a.award_description, '') ~*
        'fifty[[:space:]]*\(50\)[[:space:]]*united states'
    ) AS award_text_match
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id = o.award_transaction_id
JOIN procurement.award a
  ON a.award_id = t.award_id
WHERE r.load_batch_id IN (22, 23)
  AND a.piid = '36C10B18F2811'
GROUP BY t.fiscal_year, a.piid
ORDER BY t.fiscal_year;

\echo ''
\echo '3. Geographic keyword overlaps'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        COALESCE(t.transaction_description, '') || ' ' ||
        COALESCE(a.award_description, '') AS evidence_text
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
),
flags AS (
    SELECT
        fiscal_year,
        obligation,
        evidence_text ~* (
            'nationwide|nationally|' ||
            'fifty[[:space:]]*\(50\)[[:space:]]*united states|' ||
            'all[[:space:]]*50[[:space:]]*states'
        ) AS nationwide,
        evidence_text ~* (
            'white city|oregon|multi-state|multistate'
        ) AS multistate,
        evidence_text ~* (
            'seattle|spokane|walla walla|vancouver, wa|' ||
            'tacoma|american lake|mann-grandstaff'
        ) AS named_wa
    FROM va
)
SELECT
    fiscal_year,
    nationwide,
    multistate,
    named_wa,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS net_obligations
FROM flags
GROUP BY fiscal_year, nationwide, multistate, named_wa
ORDER BY fiscal_year, transactions DESC;

ROLLBACK;

\echo ''
\echo 'ETL-213P v0.1 COMPLETE - NO DATABASE WRITES'
