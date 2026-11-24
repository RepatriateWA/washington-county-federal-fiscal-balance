
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213Q v0.1 - VA UNRESOLVED GEOGRAPHY PRIORITIES'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. No-keyword evidence: totals by fiscal year'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.psc_code,
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
    SELECT *,
        evidence_text ~* (
            'nationwide|nationally|national scope|' ||
            'fifty[[:space:]]*\(50\)[[:space:]]*united states|' ||
            'all[[:space:]]*50[[:space:]]*states|' ||
            'throughout[[:space:]]+the[[:space:]]+united states|' ||
            'white city|oregon|multi-state|multistate|' ||
            'multiple states|across states|' ||
            'seattle|spokane|walla walla|vancouver, wa|' ||
            'tacoma|american lake|mann-grandstaff'
        ) AS has_keyword
    FROM va
)
SELECT
    fiscal_year,
    COUNT(*) AS total_transactions,
    ROUND(SUM(obligation), 2) AS total_net,
    COUNT(*) FILTER (WHERE NOT has_keyword)
        AS no_keyword_transactions,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE NOT has_keyword
    ), 0), 2) AS no_keyword_net,
    ROUND(COALESCE(SUM(ABS(obligation)) FILTER (
        WHERE NOT has_keyword
    ), 0), 2) AS no_keyword_gross_absolute
FROM flags
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. Largest PSC categories lacking keyword evidence'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.psc_code,
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
unresolved AS (
    SELECT *
    FROM va
    WHERE NOT (
        evidence_text ~* (
            'nationwide|nationally|national scope|' ||
            'fifty[[:space:]]*\(50\)[[:space:]]*united states|' ||
            'all[[:space:]]*50[[:space:]]*states|' ||
            'throughout[[:space:]]+the[[:space:]]+united states|' ||
            'white city|oregon|multi-state|multistate|' ||
            'multiple states|across states|' ||
            'seattle|spokane|walla walla|vancouver, wa|' ||
            'tacoma|american lake|mann-grandstaff'
        )
    )
)
SELECT
    u.psc_code,
    p.psc_description,
    COUNT(*) AS transactions,
    ROUND(SUM(u.obligation), 2) AS net_obligations,
    ROUND(SUM(ABS(u.obligation)), 2)
        AS gross_absolute_obligations
FROM unresolved u
LEFT JOIN procurement.psc p
  ON p.psc_code = u.psc_code
GROUP BY u.psc_code, p.psc_description
ORDER BY gross_absolute_obligations DESC
LIMIT 25;

\echo ''
\echo '3. Largest individual no-keyword transactions'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        a.piid,
        t.psc_code,
        t.federal_action_obligation AS obligation,
        c.full_fips AS county_fips,
        c.county_name,
        COALESCE(t.transaction_description, '')
            AS transaction_description,
        COALESCE(a.award_description, '')
            AS award_description,
        COALESCE(t.transaction_description, '') || ' ' ||
        COALESCE(a.award_description, '') AS evidence_text
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    LEFT JOIN procurement.place_of_performance pop
      ON pop.award_transaction_id = t.award_transaction_id
    LEFT JOIN reference.county_registry c
      ON c.county_id = pop.county_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
)
SELECT
    fiscal_year,
    award_transaction_id,
    piid,
    psc_code,
    ROUND(obligation, 2) AS obligation,
    county_fips,
    county_name,
    LEFT(transaction_description, 250)
        AS transaction_description,
    LEFT(award_description, 250)
        AS award_description
FROM va
WHERE NOT (
    evidence_text ~* (
        'nationwide|nationally|national scope|' ||
        'fifty[[:space:]]*\(50\)[[:space:]]*united states|' ||
        'all[[:space:]]*50[[:space:]]*states|' ||
        'throughout[[:space:]]+the[[:space:]]+united states|' ||
        'white city|oregon|multi-state|multistate|' ||
        'multiple states|across states|' ||
        'seattle|spokane|walla walla|vancouver, wa|' ||
        'tacoma|american lake|mann-grandstaff'
    )
)
ORDER BY ABS(obligation) DESC
LIMIT 20;

ROLLBACK;

\echo ''
\echo 'ETL-213Q v0.1 COMPLETE - NO DATABASE WRITES'
