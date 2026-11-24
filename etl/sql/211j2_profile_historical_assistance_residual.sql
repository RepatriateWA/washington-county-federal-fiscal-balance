
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211J2 - HISTORICAL ASSISTANCE RESIDUAL PROFILE'
\echo 'FY2018-FY2019'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.cfda_title AS program_title,
        c.funding_agency_name,
        c.awarding_agency_name,
        c.assistance_type_description,
        c.federal_action_obligation AS obligation,
        c.is_covid,
        c.is_extraordinary,
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
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
),
residual AS (
    SELECT *
    FROM resolved
    WHERE COALESCE(
        award_disposition,
        program_disposition,
        'UNCLASSIFIED_REVIEW'
    ) = 'UNCLASSIFIED_REVIEW'
),
summary AS (
    SELECT
        program_code,
        MAX(program_title) AS program_title,
        COUNT(DISTINCT funding_agency_name)
            AS funding_agency_count,
        STRING_AGG(
            DISTINCT funding_agency_name,
            '; '
        ) AS funding_agencies,
        COUNT(*) AS transactions,
        COUNT(*) FILTER (
            WHERE fiscal_year = 2018
        ) AS fy2018_rows,
        COUNT(*) FILTER (
            WHERE fiscal_year = 2019
        ) AS fy2019_rows,
        SUM(obligation) AS net_obligations,
        COALESCE(SUM(obligation) FILTER (
            WHERE obligation > 0
        ), 0) AS gross_positive,
        COALESCE(SUM(obligation) FILTER (
            WHERE obligation < 0
        ), 0) AS negative_adjustments,
        COUNT(*) FILTER (
            WHERE obligation < 0
        ) AS negative_rows,
        COALESCE(SUM(obligation) FILTER (
            WHERE fiscal_year = 2018
        ), 0) AS fy2018_net,
        COALESCE(SUM(obligation) FILTER (
            WHERE fiscal_year = 2019
        ), 0) AS fy2019_net,
        COUNT(*) FILTER (
            WHERE is_covid IS TRUE
        ) AS covid_rows,
        COALESCE(SUM(obligation) FILTER (
            WHERE is_covid IS TRUE
        ), 0) AS covid_net,
        COUNT(*) FILTER (
            WHERE is_extraordinary IS TRUE
        ) AS extraordinary_rows,
        COALESCE(SUM(obligation) FILTER (
            WHERE is_extraordinary IS TRUE
        ), 0) AS extraordinary_net
    FROM residual
    GROUP BY program_code
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY ABS(net_obligations) DESC,
                 program_code NULLS LAST
    ) AS priority_rank,
    program_code,
    program_title,
    funding_agency_count,
    funding_agencies,
    transactions,
    fy2018_rows,
    fy2019_rows,
    ROUND(net_obligations, 2) AS net_obligations,
    ROUND(gross_positive, 2) AS gross_positive,
    ROUND(negative_adjustments, 2)
        AS negative_adjustments,
    negative_rows,
    ROUND(fy2018_net, 2) AS fy2018_net,
    ROUND(fy2019_net, 2) AS fy2019_net,
    covid_rows,
    ROUND(covid_net, 2) AS covid_net,
    extraordinary_rows,
    ROUND(extraordinary_net, 2)
        AS extraordinary_net
FROM summary
ORDER BY priority_rank
LIMIT 30;

ROLLBACK;

\echo 'ETL-211J2 COMPLETE - NO DATABASE WRITES'
