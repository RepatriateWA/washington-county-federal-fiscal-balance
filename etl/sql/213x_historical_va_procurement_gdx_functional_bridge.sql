
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '=========================================================='
\echo 'ETL-213X v0.1 - HISTORICAL VA PROCUREMENT / GDX BRIDGE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '=========================================================='

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Verify GDX component-to-control reconciliation'

WITH totals AS (
    SELECT
        e.fiscal_year,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_total,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_total
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year IN (2018, 2019)
    GROUP BY e.fiscal_year
)
SELECT
    fiscal_year,
    ROUND(component_total, 2) AS component_total,
    ROUND(control_total, 2) AS control_total,
    ROUND(component_total - control_total, 2)
        AS reconciliation_difference
FROM totals
ORDER BY fiscal_year;

\echo ''
\echo '2. Procurement functional screening by PSC'

WITH procurement AS (
    SELECT
        t.fiscal_year,
        t.psc_code,
        t.federal_action_obligation AS obligation,
        CASE
            WHEN t.psc_code IN (
                '6525', '6515', 'Q402', 'Q201', 'Q999'
            )
            OR t.psc_code LIKE 'Q%'
                THEN 'MEDICAL_CARE_CANDIDATE'
            WHEN t.psc_code LIKE 'Y%'
              OR t.psc_code LIKE 'Z%'
                THEN 'CONSTRUCTION_FACILITIES_CANDIDATE'
            WHEN t.psc_code LIKE 'D%'
                THEN 'IT_TELECOM_UNRESOLVED'
            ELSE 'OTHER_UNRESOLVED'
        END AS screening_family
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id =
         r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id =
         o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(
          r.raw_record->>'funding_agency_code'
      ) = '036'
      AND t.fiscal_year IN (2018, 2019)
)
SELECT
    fiscal_year,
    screening_family,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS net_obligations,
    ROUND(SUM(ABS(obligation)), 2)
        AS gross_absolute_obligations
FROM procurement
GROUP BY fiscal_year, screening_family
ORDER BY fiscal_year, screening_family;

\echo ''
\echo '3. Largest procurement PSCs with GDX candidate family'

WITH procurement AS (
    SELECT
        t.fiscal_year,
        t.psc_code,
        t.federal_action_obligation AS obligation
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id =
         r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id =
         o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(
          r.raw_record->>'funding_agency_code'
      ) = '036'
      AND t.fiscal_year IN (2018, 2019)
)
SELECT
    p.fiscal_year,
    p.psc_code,
    s.psc_description,
    COUNT(*) AS transactions,
    ROUND(SUM(p.obligation), 2) AS net_obligations,
    ROUND(SUM(ABS(p.obligation)), 2)
        AS gross_absolute_obligations
FROM procurement p
LEFT JOIN procurement.psc s
  ON s.psc_code = p.psc_code
GROUP BY
    p.fiscal_year,
    p.psc_code,
    s.psc_description
ORDER BY
    p.fiscal_year,
    gross_absolute_obligations DESC
LIMIT 40;

ROLLBACK;

\echo ''
\echo 'ETL-213X v0.1 COMPLETE - NO DATABASE WRITES'
