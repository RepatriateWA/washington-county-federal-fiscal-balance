
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211K2 - HISTORICAL VA EFFECTIVE DISPOSITION AUDIT'
\echo 'FY2018-FY2019 | READ ONLY | NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. CROSSWALK CANDIDATES AND EFFECTIVE RESOLUTION'
\echo '------------------------------------------------------------'

WITH crosswalk(program_code, gdx_family) AS (
    VALUES
    ('64.109','COMPENSATION_PENSION'),
    ('64.110','COMPENSATION_PENSION'),
    ('64.104','COMPENSATION_PENSION'),
    ('64.105','COMPENSATION_PENSION'),
    ('64.028','EDUCATION_VRE'),
    ('64.117','EDUCATION_VRE'),
    ('64.124','EDUCATION_VRE'),
    ('64.032','EDUCATION_VRE'),
    ('64.120','EDUCATION_VRE'),
    ('64.041','MEDICAL_CARE'),
    ('64.045','MEDICAL_CARE'),
    ('64.012','MEDICAL_CARE'),
    ('64.040','MEDICAL_CARE'),
    ('64.048','MEDICAL_CARE'),
    ('64.047','MEDICAL_CARE'),
    ('64.013','MEDICAL_CARE'),
    ('64.050','MEDICAL_CARE'),
    ('64.039','MEDICAL_CARE'),
    ('64.049','MEDICAL_CARE'),
    ('64.042','MEDICAL_CARE'),
    ('64.044','MEDICAL_CARE'),
    ('64.011','MEDICAL_CARE'),
    ('64.046','MEDICAL_CARE'),
    ('64.043','MEDICAL_CARE'),
    ('64.005','CONSTRUCTION'),
    ('64.101','MEMORIAL_BENEFITS'),
    ('64.203','MEMORIAL_BENEFITS'),
    ('64.206','MEMORIAL_BENEFITS')
),
historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
),
resolved AS (
    SELECT
        h.*,
        x.gdx_family,
        p.match_count AS program_matches,
        a.match_count AS award_matches,
        p.disposition AS program_disposition,
        a.disposition AS award_disposition,
        COALESCE(
            a.disposition,
            p.disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS final_disposition
    FROM historical h
    JOIN crosswalk x
      ON x.program_code = h.program_code
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS match_count,
            MIN(m.resolved_accounting_disposition)
                AS disposition
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = h.program_code
          AND h.fiscal_year BETWEEN
              COALESCE(m.valid_from_fiscal_year, -9999)
              AND COALESCE(m.valid_through_fiscal_year, 9999)
    ) p ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS match_count,
            MIN(a.accounting_disposition)
                AS disposition
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = h.program_code
          AND a.source_award_identifier = h.award_identifier
          AND h.fiscal_year BETWEEN
              COALESCE(a.valid_from_fiscal_year, -9999)
              AND COALESCE(a.valid_through_fiscal_year, 9999)
    ) a ON TRUE
),
gdx_presence AS (
    SELECT DISTINCT
        e.fiscal_year,
        c.category_code
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year IN (2018, 2019)
      AND c.aggregation_role = 'COMPONENT'
)
SELECT
    r.fiscal_year,
    r.program_code,
    r.gdx_family,
    CASE
        WHEN g.category_code IS NOT NULL THEN 'PRESENT'
        ELSE 'ABSENT'
    END AS historical_gdx_family,
    r.final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(r.obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE r.program_matches > 1
    ) AS multiple_program_matches,
    COUNT(*) FILTER (
        WHERE r.award_matches > 1
    ) AS multiple_award_matches,
    COUNT(*) FILTER (
        WHERE r.program_disposition IS NOT NULL
          AND r.award_disposition IS NOT NULL
          AND r.program_disposition <> r.award_disposition
    ) AS disposition_conflicts
FROM resolved r
LEFT JOIN gdx_presence g
  ON g.fiscal_year = r.fiscal_year
 AND g.category_code = r.gdx_family
GROUP BY
    r.fiscal_year,
    r.program_code,
    r.gdx_family,
    g.category_code,
    r.final_disposition
ORDER BY
    r.fiscal_year,
    ABS(SUM(r.obligation)) DESC,
    r.program_code,
    r.final_disposition;

\echo ''
\echo '2. HISTORICAL CROSSWALK ACCOUNTING SUMMARY'
\echo '------------------------------------------------------------'

WITH crosswalk(program_code, gdx_family) AS (
    VALUES
    ('64.109','COMPENSATION_PENSION'),
    ('64.110','COMPENSATION_PENSION'),
    ('64.104','COMPENSATION_PENSION'),
    ('64.105','COMPENSATION_PENSION'),
    ('64.028','EDUCATION_VRE'),
    ('64.117','EDUCATION_VRE'),
    ('64.124','EDUCATION_VRE'),
    ('64.032','EDUCATION_VRE'),
    ('64.120','EDUCATION_VRE'),
    ('64.041','MEDICAL_CARE'),
    ('64.045','MEDICAL_CARE'),
    ('64.012','MEDICAL_CARE'),
    ('64.040','MEDICAL_CARE'),
    ('64.048','MEDICAL_CARE'),
    ('64.047','MEDICAL_CARE'),
    ('64.013','MEDICAL_CARE'),
    ('64.050','MEDICAL_CARE'),
    ('64.039','MEDICAL_CARE'),
    ('64.049','MEDICAL_CARE'),
    ('64.042','MEDICAL_CARE'),
    ('64.044','MEDICAL_CARE'),
    ('64.011','MEDICAL_CARE'),
    ('64.046','MEDICAL_CARE'),
    ('64.043','MEDICAL_CARE'),
    ('64.005','CONSTRUCTION'),
    ('64.101','MEMORIAL_BENEFITS'),
    ('64.203','MEMORIAL_BENEFITS'),
    ('64.206','MEMORIAL_BENEFITS')
),
historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
),
resolved AS (
    SELECT
        h.*,
        x.gdx_family,
        p.match_count AS program_matches,
        a.match_count AS award_matches,
        p.disposition AS program_disposition,
        a.disposition AS award_disposition,
        COALESCE(
            a.disposition,
            p.disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS final_disposition
    FROM historical h
    JOIN crosswalk x
      ON x.program_code = h.program_code
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS match_count,
            MIN(m.resolved_accounting_disposition)
                AS disposition
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = h.program_code
          AND h.fiscal_year BETWEEN
              COALESCE(m.valid_from_fiscal_year, -9999)
              AND COALESCE(m.valid_through_fiscal_year, 9999)
    ) p ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS match_count,
            MIN(a.accounting_disposition)
                AS disposition
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = h.program_code
          AND a.source_award_identifier = h.award_identifier
          AND h.fiscal_year BETWEEN
              COALESCE(a.valid_from_fiscal_year, -9999)
              AND COALESCE(a.valid_through_fiscal_year, 9999)
    ) a ON TRUE
),
gdx_presence AS (
    SELECT DISTINCT
        e.fiscal_year,
        c.category_code
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year IN (2018, 2019)
      AND c.aggregation_role = 'COMPONENT'
)
SELECT
    r.fiscal_year,
    r.gdx_family,
    CASE
        WHEN g.category_code IS NOT NULL THEN 'PRESENT'
        ELSE 'ABSENT'
    END AS historical_gdx_family,
    r.final_disposition,
    COUNT(*) AS transactions,
    COUNT(DISTINCT r.program_code) AS programs,
    ROUND(SUM(r.obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE r.program_matches > 1
           OR r.award_matches > 1
    ) AS multiple_policy_match_transactions,
    COUNT(*) FILTER (
        WHERE r.program_disposition IS NOT NULL
          AND r.award_disposition IS NOT NULL
          AND r.program_disposition <> r.award_disposition
    ) AS conflicting_disposition_transactions
FROM resolved r
LEFT JOIN gdx_presence g
  ON g.fiscal_year = r.fiscal_year
 AND g.category_code = r.gdx_family
GROUP BY
    r.fiscal_year,
    r.gdx_family,
    g.category_code,
    r.final_disposition
ORDER BY
    r.fiscal_year,
    r.gdx_family,
    r.final_disposition;

ROLLBACK;

\echo ''
\echo 'ETL-211K2 COMPLETE - NO DATABASE WRITES'
