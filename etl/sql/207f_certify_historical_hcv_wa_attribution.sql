\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-207F - HISTORICAL HCV WA ATTRIBUTION CERTIFICATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

WITH hcv AS (
    SELECT
        c.load_batch_id,
        c.action_date_fiscal_year AS fiscal_year,
        c.source_row_number,
        c.federal_action_obligation,
        r.raw_assistance_transaction_id,
        r.raw_record,
        (
            r.raw_record ->> 'recipient_state_code' = 'WA'
            AND r.raw_record ->>
                'prime_award_transaction_recipient_state_fips_code' = '53'
            AND r.raw_record ->>
                'prime_award_transaction_place_of_performance_state_fips_code' = '53'
            AND r.raw_record ->>
                'primary_place_of_performance_state_name' = 'WASHINGTON'
        ) IS TRUE AS wa_geography_pass,
        (
            r.raw_record ->> 'funding_agency_code' = '086'
            AND r.raw_record ->> 'awarding_agency_code' = '086'
        ) IS TRUE AS hud_agency_pass,
        (
            NULLIF(BTRIM(r.raw_record ->> 'recipient_name'), '') IS NOT NULL
            AND NULLIF(BTRIM(r.raw_record ->> 'recipient_uei'), '') IS NOT NULL
        ) IS TRUE AS recipient_identity_pass
    FROM analysis.v_certified_assistance_ledger c
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE TRIM(c.cfda_number) = '14.871'
      AND (
           (c.load_batch_id = 20 AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21 AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations,
    COUNT(*) FILTER (
        WHERE raw_assistance_transaction_id IS NULL
    ) AS missing_raw_records,
    COUNT(*) FILTER (
        WHERE NOT wa_geography_pass
    ) AS wa_geography_exceptions,
    COALESCE(SUM(federal_action_obligation) FILTER (
        WHERE NOT wa_geography_pass
    ), 0) AS wa_geography_exception_dollars,
    COUNT(*) FILTER (
        WHERE NOT hud_agency_pass
    ) AS hud_agency_exceptions,
    COUNT(*) FILTER (
        WHERE NOT recipient_identity_pass
    ) AS recipient_identity_exceptions,
    COUNT(*) FILTER (
        WHERE wa_geography_pass
          AND hud_agency_pass
          AND recipient_identity_pass
    ) AS fully_verified_transactions,
    COALESCE(SUM(federal_action_obligation) FILTER (
        WHERE wa_geography_pass
          AND hud_agency_pass
          AND recipient_identity_pass
    ), 0) AS fully_verified_dollars
FROM hcv
GROUP BY fiscal_year
ORDER BY fiscal_year;

COMMIT;

\echo 'ETL-207F READ-ONLY CERTIFICATION COMPLETE'